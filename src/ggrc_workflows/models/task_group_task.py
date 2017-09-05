# Copyright (C) 2017 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""A module containing the workflow TaskGroupTask model."""


import datetime

from sqlalchemy import orm
from sqlalchemy import schema

from ggrc import db
from ggrc.builder import simple_property
from ggrc.fulltext.mixin import Indexed
from ggrc.login import get_current_user
from ggrc.models import mixins
from ggrc.models.types import JsonType
from ggrc.models import reflection
from ggrc_workflows.models.task_group import TaskGroup
from ggrc_workflows.models import mixins as wf_mixins


class TaskGroupTask(mixins.WithContact,
                    mixins.Titled,
                    mixins.Described,
                    wf_mixins.CheckMappedContact,
                    mixins.Slugged,
                    mixins.Timeboxed,
                    Indexed,
                    db.Model):
  """Workflow TaskGroupTask model."""

  __tablename__ = 'task_group_tasks'
  _extra_table_args = (
      schema.CheckConstraint('start_date <= end_date'),
  )
  _title_uniqueness = False
  _start_changed = False

  @classmethod
  def default_task_type(cls):
    return cls.TEXT

  @classmethod
  def generate_slug_prefix(cls):
    return "TASK"

  task_group_id = db.Column(
      db.Integer,
      db.ForeignKey('task_groups.id', ondelete="CASCADE"),
      nullable=False,
  )
  sort_index = db.Column(
      db.String(length=250), default="", nullable=False)

  object_approval = db.Column(
      db.Boolean, nullable=False, default=False)

  task_type = db.Column(
      db.String(length=250), default=default_task_type, nullable=False)

  response_options = db.Column(
      JsonType(), nullable=False, default=[])

  TEXT = 'text'
  MENU = 'menu'
  CHECKBOX = 'checkbox'
  VALID_TASK_TYPES = [TEXT, MENU, CHECKBOX]

  @orm.validates('task_type')
  def validate_task_type(self, key, value):
    # pylint: disable=unused-argument
    if value is None:
      value = self.default_task_type()
    if value not in self.VALID_TASK_TYPES:
      raise ValueError(u"Invalid type '{}'".format(value))
    return value

  # pylint: disable=unused-argument
  @orm.validates("start_date", "end_date")
  def validate_date(self, key, value):
    """Validates date's itself correctness, start_ end_ dates relative to each
    other correctness is checked with 'before_insert' hook
    """
    if value is None:
      return
    if isinstance(value, datetime.datetime):
      value = value.date()
    if value < datetime.date(100, 1, 1):
      current_century = datetime.date.today().year / 100
      return datetime.date(value.year + current_century * 100,
                           value.month,
                           value.day)
    return value

  _api_attrs = reflection.ApiAttributes(
      'task_group',
      'sort_index',
      'object_approval',
      'task_type',
      'response_options',
      reflection.Attribute('view_start_date', update=False, create=False),
      reflection.Attribute('view_end_date', update=False, create=False),
  )
  _sanitize_html = []
  _aliases = {
      "title": "Summary",
      "description": {
          "display_name": "Task Description",
          "handler_key": "task_description",
      },
      "secondary_contact": None,
      "contact": {
          "mandatory": True,
          "display_name": "Assignee",
      },
      "start_date": {
          "display_name": "Start Date",
          "mandatory": True,
          "description": (
              "Enter the task start date\nin the following format:\n"
              "'mm/dd/yyyy'"
          ),
      },
      "end_date": {
          "display_name": "End Date",
          "mandatory": True,
          "description": (
              "Enter the task end date\nin the following format:\n"
              "'mm/dd/yyyy'"
          ),
      },
      "task_group": {
          "display_name": "Task Group",
          "mandatory": True,
          "filter_by": "_filter_by_task_group",
      },
      "task_type": {
          "display_name": "Task Type",
          "mandatory": True,
          "description": ("Accepted values are:"
                          "\n'Rich Text'\n'Dropdown'\n'Checkbox'"),
      }
  }

  @classmethod
  def _filter_by_task_group(cls, predicate):
    return TaskGroup.query.filter(
        (TaskGroup.id == cls.task_group_id) &
        (predicate(TaskGroup.slug) | predicate(TaskGroup.title))
    ).exists()

  def _get_view_date(self, date):
    if date and self.task_group and self.task_group.workflow:
      return self.task_group.workflow.calc_next_adjusted_date(date)

  @simple_property
  def view_start_date(self):
    return self._get_view_date(self.start_date)

  @simple_property
  def view_end_date(self):
    return self._get_view_date(self.end_date)

  @classmethod
  def eager_query(cls):
    query = super(TaskGroupTask, cls).eager_query()
    return query.options(
        orm.subqueryload('task_group'),
    )

  def _display_name(self):
    return self.title + '<->' + self.task_group.display_name

  def copy(self, _other=None, **kwargs):
    columns = [
        'title', 'description',
        'task_group', 'sort_index',
        'start_date', 'end_date',
        'contact', 'modified_by',
        'task_type', 'response_options',
    ]

    contact = None
    if kwargs.get('clone_people', False):
      contact = self.contact
    else:
      contact = get_current_user()

    kwargs['modified_by'] = get_current_user()

    target = self.copy_into(_other, columns, contact=contact, **kwargs)
    return target

  @property
  def workflow(self):
    return getattr(self.task_group, 'workflow', None)
