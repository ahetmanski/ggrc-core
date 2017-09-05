# Copyright (C) 2017 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""A module containing the workflow TaskGroup model."""


from sqlalchemy import or_

from ggrc import db
from ggrc.fulltext.mixin import Indexed
from ggrc.login import get_current_user
from ggrc.models.associationproxy import association_proxy
from ggrc.models.mixins import (
    Titled, Slugged, Described, Timeboxed, WithContact
)
from ggrc.models.reflection import AttributeInfo
from ggrc.models import reflection
from ggrc.models import all_models
from ggrc_workflows.models import mixins as wf_mixins
from ggrc_workflows.models.task_group_object import TaskGroupObject


class TaskGroup(WithContact, Timeboxed, Described, Titled,
                wf_mixins.CheckMappedContact, Slugged, Indexed, db.Model):
  """Workflow TaskGroup model."""

  __tablename__ = 'task_groups'
  _title_uniqueness = False

  workflow_id = db.Column(
      db.Integer,
      db.ForeignKey('workflows.id', ondelete="CASCADE"),
      nullable=False,
  )
  lock_task_order = db.Column(db.Boolean(), nullable=True)

  task_group_objects = db.relationship(
      'TaskGroupObject', backref='task_group', cascade='all, delete-orphan')

  objects = association_proxy(
      'task_group_objects', 'object', 'TaskGroupObject')

  task_group_tasks = db.relationship(
      'TaskGroupTask', backref='task_group', cascade='all, delete-orphan')

  cycle_task_groups = db.relationship(
      'CycleTaskGroup', backref='task_group')

  sort_index = db.Column(
      db.String(length=250), default="", nullable=False)

  _api_attrs = reflection.ApiAttributes(
      'workflow',
      'task_group_objects',
      reflection.Attribute('objects', create=False, update=False),
      'task_group_tasks',
      'lock_task_order',
      'sort_index',
      # Intentionally do not include `cycle_task_groups`
      # 'cycle_task_groups',
  )

  _aliases = {
      "title": "Summary",
      "description": "Details",
      "contact": {
          "display_name": "Assignee",
          "mandatory": True,
      },
      "secondary_contact": None,
      "start_date": None,
      "end_date": None,
      "workflow": {
          "display_name": "Workflow",
          "mandatory": True,
          "filter_by": "_filter_by_workflow",
      },
      "task_group_objects": {
          "display_name": "Objects",
          "type": AttributeInfo.Type.SPECIAL_MAPPING,
          "filter_by": "_filter_by_objects",
      },
  }

  def copy(self, _other=None, **kwargs):
    columns = [
        'title', 'description', 'workflow', 'sort_index', 'modified_by',
        'context'
    ]

    if kwargs.get('clone_people', False) and getattr(self, "contact"):
      columns.append("contact")
    else:
      kwargs["contact"] = get_current_user()

    target = self.copy_into(_other, columns, **kwargs)

    if kwargs.get('clone_objects', False):
      self.copy_objects(target, **kwargs)

    if kwargs.get('clone_tasks', False):
      self.copy_tasks(target, **kwargs)

    return target

  def copy_objects(self, target, **kwargs):
    # pylint: disable=unused-argument
    for task_group_object in self.task_group_objects:
      target.task_group_objects.append(task_group_object.copy(
          task_group=target,
          context=target.context,
      ))

    return target

  def copy_tasks(self, target, **kwargs):
    for task_group_task in self.task_group_tasks:
      target.task_group_tasks.append(task_group_task.copy(
          None,
          task_group=target,
          context=target.context,
          clone_people=kwargs.get("clone_people", False),
      ))

    return target

  @classmethod
  def _filter_by_workflow(cls, predicate):
    from ggrc_workflows.models import Workflow
    return Workflow.query.filter(
        (Workflow.id == cls.workflow_id) &
        (predicate(Workflow.slug) | predicate(Workflow.title))
    ).exists()

  @classmethod
  def _filter_by_objects(cls, predicate):
    parts = []
    for model_name in all_models.__all__:
      model = getattr(all_models, model_name)
      query = getattr(model, "query", None)
      field = getattr(model, "slug", getattr(model, "email", None))
      if query is None or field is None or not hasattr(model, "id"):
        continue
      parts.append(query.filter(
          (TaskGroupObject.object_type == model_name) &
          (model.id == TaskGroupObject.object_id) &
          predicate(field)
      ).exists())
    return TaskGroupObject.query.filter(
        (TaskGroupObject.task_group_id == cls.id) &
        or_(*parts)
    ).exists()
