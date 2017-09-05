# Copyright (C) 2017 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Module containing Cycle tasks.
"""

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declared_attr

from ggrc import builder
from ggrc import db
from ggrc.fulltext import attributes as ft_attributes
from ggrc.fulltext import mixin as ft_mixin
from ggrc import login
from ggrc.models import mixins
from ggrc.models import reflection
from ggrc.models import relationship
from ggrc.models import types
from ggrc_workflows.models.cycle import Cycle
from ggrc_workflows.models.cycle_task_group import CycleTaskGroup
from ggrc_workflows.models import mixins as wf_mixins


class CycleTaskGroupObjectTask(mixins.WithContact,
                               wf_mixins.CycleTaskStatusValidatedMixin,
                               mixins.Stateful,
                               mixins.Timeboxed,
                               relationship.Relatable,
                               mixins.Notifiable,
                               mixins.Described,
                               wf_mixins.CheckMappedContact,
                               mixins.Titled,
                               mixins.Slugged,
                               mixins.Base,
                               ft_mixin.Indexed,
                               db.Model):
  """Cycle task model
  """
  __tablename__ = 'cycle_task_group_object_tasks'

  readable_name_alias = 'cycle task'

  _title_uniqueness = False

  IMPORTABLE_FIELDS = (
      'slug', 'title', 'description', 'start_date',
      'end_date', 'finished_date', 'verified_date',
      'contact',
  )

  @classmethod
  def generate_slug_prefix(cls):
    return "CYCLETASK"

  # Note: this statuses are used in utils/query_helpers to filter out the tasks
  # that should be visible on My Tasks pages.

  PROPERTY_TEMPLATE = u"task {}"

  _fulltext_attrs = [
      ft_attributes.DateFullTextAttr("end_date", 'end_date',),
      ft_attributes.FullTextAttr("assignee", 'contact', ['name', 'email']),
      ft_attributes.FullTextAttr("group title",
                                 'cycle_task_group',
                                 ['title'],
                                 False),
      ft_attributes.FullTextAttr("cycle title", 'cycle', ['title'], False),
      ft_attributes.FullTextAttr("group assignee",
                                 lambda x: x.cycle_task_group.contact,
                                 ['email', 'name'],
                                 False),
      ft_attributes.FullTextAttr("cycle assignee",
                                 lambda x: x.cycle.contact,
                                 ['email', 'name'],
                                 False),
      ft_attributes.DateFullTextAttr(
          "group due date",
          lambda x: x.cycle_task_group.next_due_date,
          with_template=False),
      ft_attributes.DateFullTextAttr("cycle due date",
                                     lambda x: x.cycle.next_due_date,
                                     with_template=False),
      ft_attributes.MultipleSubpropertyFullTextAttr("comments",
                                                    "cycle_task_entries",
                                                    ["description"]),
  ]

  AUTO_REINDEX_RULES = [
      ft_mixin.ReindexRule("CycleTaskEntry",
                           lambda x: x.cycle_task_group_object_task),
  ]

  cycle_id = db.Column(
      db.Integer,
      db.ForeignKey('cycles.id', ondelete="CASCADE"),
      nullable=False,
  )
  cycle_task_group_id = db.Column(
      db.Integer,
      db.ForeignKey('cycle_task_groups.id', ondelete="CASCADE"),
      nullable=False,
  )
  task_group_task_id = db.Column(
      db.Integer, db.ForeignKey('task_group_tasks.id'), nullable=True)
  task_group_task = db.relationship(
      "TaskGroupTask",
      foreign_keys="CycleTaskGroupObjectTask.task_group_task_id"
  )
  task_type = db.Column(db.String(length=250), nullable=False)
  response_options = db.Column(types.JsonType(), nullable=False, default=[])
  selected_response_options = db.Column(types.JsonType(),
                                        nullable=False,
                                        default=[])

  sort_index = db.Column(db.String(length=250), default="", nullable=False)

  finished_date = db.Column(db.DateTime)
  verified_date = db.Column(db.DateTime)

  object_approval = association_proxy('cycle', 'workflow.object_approval')
  object_approval.publish_raw = True

  @property
  def cycle_task_objects_for_cache(self):
    """Changing task state must invalidate `workflow_state` on objects
    """
    return [(object_.__class__.__name__, object_.id) for object_ in
            self.related_objects]  # pylint: disable=not-an-iterable

  _api_attrs = reflection.ApiAttributes(
      'cycle',
      'cycle_task_group',
      'task_group_task',
      'cycle_task_entries',
      'sort_index',
      'task_type',
      'response_options',
      'selected_response_options',
      reflection.Attribute('object_approval', create=False, update=False),
      reflection.Attribute('finished_date', create=False, update=False),
      reflection.Attribute('verified_date', create=False, update=False),
      reflection.Attribute('allow_change_state', create=False, update=False),
  )

  default_description = "<ol>"\
                        + "<li>Expand the object review task.</li>"\
                        + "<li>Click on the Object to be reviewed.</li>"\
                        + "<li>Review the object in the Info tab.</li>"\
                        + "<li>Click \"Approve\" to approve the object.</li>"\
                        + "<li>Click \"Decline\" to decline the object.</li>"\
                        + "</ol>"

  _aliases = {
      "title": "Summary",
      "description": "Task Details",
      "contact": {
          "display_name": "Assignee",
          "mandatory": True,
      },
      "secondary_contact": None,
      "finished_date": "Actual Finish Date",
      "verified_date": "Actual Verified Date",
      "cycle": {
          "display_name": "Cycle",
          "filter_by": "_filter_by_cycle",
      },
      "cycle_task_group": {
          "display_name": "Task Group",
          "mandatory": True,
          "filter_by": "_filter_by_cycle_task_group",
      },
      "task_type": {
          "display_name": "Task Type",
          "mandatory": True,
      },
      "end_date": "Due Date",
      "start_date": "Start Date",
  }

  @builder.simple_property
  def related_objects(self):
    """Compute and return a list of all the objects related to this cycle task.

    Related objects are those that are found either on the "source" side, or
    on the "destination" side of any of the instance's relations.

    Returns:
      (list) All objects related to the instance.
    """
    # pylint: disable=not-an-iterable
    sources = [r.source for r in self.related_sources]
    destinations = [r.destination for r in self.related_destinations]
    return sources + destinations

  @declared_attr
  def wfo_roles(self):
    """WorkflowOwner UserRoles in parent Workflow.

    Relies on self.context_id = parent_workflow.context_id.
    """
    from ggrc_basic_permissions import models as bp_models

    def primaryjoin():
      """Join UserRoles by context_id = self.context_id and role_id = WFO."""
      workflow_owner_role_id = db.session.query(
          bp_models.Role.id,
      ).filter(
          bp_models.Role.name == "WorkflowOwner",
      ).subquery()
      ur_context_id = sa.orm.foreign(bp_models.UserRole.context_id)
      ur_role_id = sa.orm.foreign(bp_models.UserRole.role_id)
      return sa.and_(self.context_id == ur_context_id,
                     workflow_owner_role_id == ur_role_id)

    return db.relationship(
        bp_models.UserRole,
        primaryjoin=primaryjoin,
        viewonly=True,
    )

  @builder.simple_property
  def allow_change_state(self):
    return self.cycle.is_current and self.current_user_wfo_or_assignee()

  def current_user_wfo_or_assignee(self):
    """Current user is Workflow owner or Assignee for self."""
    current_user_id = login.get_current_user_id()

    # pylint: disable=not-an-iterable
    return (current_user_id == self.contact_id or
            current_user_id in [ur.person_id for ur in self.wfo_roles])

  @classmethod
  def _filter_by_cycle(cls, predicate):
    """Get query that filters cycle tasks by related cycles.

    Args:
      predicate: lambda function that excepts a single parameter and returns
      true of false.

    Returns:
      An sqlalchemy query that evaluates to true or false and can be used in
      filtering cycle tasks by related cycles.
    """
    return Cycle.query.filter(
        (Cycle.id == cls.cycle_id) &
        (predicate(Cycle.slug) | predicate(Cycle.title))
    ).exists()

  @classmethod
  def _filter_by_cycle_task_group(cls, predicate):
    """Get query that filters cycle tasks by related cycle task groups.

    Args:
      predicate: lambda function that excepts a single parameter and returns
      true of false.

    Returns:
      An sqlalchemy query that evaluates to true or false and can be used in
      filtering cycle tasks by related cycle task groups.
    """
    return CycleTaskGroup.query.filter(
        (CycleTaskGroup.id == cls.cycle_id) &
        (predicate(CycleTaskGroup.slug) | predicate(CycleTaskGroup.title))
    ).exists()

  @classmethod
  def eager_query(cls):
    """Add cycle task entries to cycle task eager query

    This function adds cycle_task_entries as a join option when fetching cycles
    tasks, and makes sure that with one query we fetch all cycle task related
    data needed for generating cycle taks json for a response.

    Returns:
      a query object with cycle_task_entries added to joined load options.
    """
    query = super(CycleTaskGroupObjectTask, cls).eager_query()
    return query.options(
        orm.joinedload('cycle')
           .joinedload('workflow')
           .undefer_group('Workflow_complete'),
        orm.joinedload('cycle_task_entries'),
        orm.subqueryload('wfo_roles'),
    )

  @classmethod
  def indexed_query(cls):
    return super(CycleTaskGroupObjectTask, cls).indexed_query().options(
        orm.Load(cls).load_only(
            "end_date",
            "start_date",
            "created_at",
            "updated_at"
        ),
        orm.Load(cls).joinedload("cycle_task_group").load_only(
            "id",
            "title",
            "end_date",
            "next_due_date",
        ),
        orm.Load(cls).joinedload("cycle").load_only(
            "id",
            "title",
            "next_due_date"
        ),
        orm.Load(cls).joinedload("cycle_task_group").joinedload(
            "contact"
        ).load_only(
            "email",
            "name",
            "id"
        ),
        orm.Load(cls).joinedload("cycle").joinedload(
            "contact"
        ).load_only(
            "email",
            "name",
            "id"
        ),
        orm.Load(cls).subqueryload("cycle_task_entries").load_only(
            "description",
            "id"
        ),
        orm.Load(cls).joinedload("contact").load_only(
            "email",
            "name",
            "id"
        ),
    )

  @property
  def workflow(self):
    return getattr(self.cycle, 'workflow', None)


class CycleTaskable(object):
  """ Requires the Relatable mixin, otherwise cycle_task_group_object_tasks
  fails to fetch related objects
  """
  @builder.simple_property
  def cycle_task_group_object_tasks(self):
    """ Lists all the cycle tasks related to a certain object
    """
    sources = [r.CycleTaskGroupObjectTask_source
               for r in self.related_sources
               if r.CycleTaskGroupObjectTask_source is not None]
    destinations = [r.CycleTaskGroupObjectTask_destination
                    for r in self.related_destinations
                    if r.CycleTaskGroupObjectTask_destination is not None]
    return sources + destinations

  @classmethod
  def eager_query(cls):
    query = super(CycleTaskable, cls).eager_query()
    return query.options(
        orm.subqueryload('related_sources')
           .joinedload('CycleTaskGroupObjectTask_source')
           .undefer_group('CycleTaskGroupObjectTask_complete')
           .joinedload('cycle'),
        orm.subqueryload('related_destinations')
           .joinedload('CycleTaskGroupObjectTask_destination')
           .undefer_group('CycleTaskGroupObjectTask_complete')
           .joinedload('cycle')
    )
