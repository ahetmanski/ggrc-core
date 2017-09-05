# Copyright (C) 2017 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

# pylint: disable=redefined-outer-name

from datetime import datetime, date
from flask import Blueprint
from logging import getLogger
from sqlalchemy import inspect, and_, orm

from ggrc import db
from ggrc.login import get_current_user
from ggrc.models import all_models
from ggrc.models.relationship import Relationship
from ggrc.rbac.permissions import is_allowed_update
from ggrc.services import signals
from ggrc.services.common import log_event
from ggrc.services.registry import service
from ggrc_workflows import models, notification
from ggrc_workflows.models import relationship_helper
from ggrc_workflows.models import WORKFLOW_OBJECT_TYPES
from ggrc_workflows.notification import pusher
from ggrc_workflows.converters import IMPORTABLE, EXPORTABLE
from ggrc_workflows.converters.handlers import COLUMN_HANDLERS
from ggrc_workflows.services.common import Signals
from ggrc_workflows.roles import (
    WorkflowOwner, WorkflowMember, BasicWorkflowReader, WorkflowBasicReader,
    WorkflowEditor
)
from ggrc_basic_permissions.models import Role, UserRole, ContextImplication
from ggrc_basic_permissions.contributed_roles import (
    RoleContributions, RoleDeclarations, DeclarativeRoleImplications
)


# pylint: disable=invalid-name
logger = getLogger(__name__)


# Initialize Flask Blueprint for extension
blueprint = Blueprint(
    'ggrc_workflows',
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/static/ggrc_workflows',
)


for type_ in WORKFLOW_OBJECT_TYPES:
  model = getattr(all_models, type_)
  model.__bases__ = (
      models.task_group_object.TaskGroupable,
      models.cycle_task_group_object_task.CycleTaskable,
      models.workflow.WorkflowState,
  ) + model.__bases__
  model.late_init_task_groupable()


def get_public_config(current_user):  # noqa
  """Expose additional permissions-dependent config to client.
  """
  return {}

# Initialize service endpoints


def contributed_services():
  return [
      service('workflows', models.Workflow),
      service('workflow_people', models.WorkflowPerson),
      service('task_groups', models.TaskGroup),
      service('task_group_tasks', models.TaskGroupTask),
      service('task_group_objects', models.TaskGroupObject),

      service('cycles', models.Cycle),
      service('cycle_task_entries', models.CycleTaskEntry),
      service('cycle_task_groups', models.CycleTaskGroup),
      service('cycle_task_group_object_tasks', models.CycleTaskGroupObjectTask)
  ]


def contributed_object_views():
  """Contributed object views"""
  from ggrc.views.registry import object_view

  return [
      object_view(models.Workflow),
  ]


def _get_min_next_due_date(due_dated_objects):
  next_due_date = None

  for obj in due_dated_objects:
    if not obj.is_done:
      obj_next_due_date = obj.next_due_date
      if isinstance(obj_next_due_date, datetime):
        obj_next_due_date = obj_next_due_date.date()
      if obj_next_due_date is not None:
        if next_due_date is None or next_due_date > obj_next_due_date:
          next_due_date = obj_next_due_date

  return next_due_date


def _get_min_end_date(timeboxed_objects):
  end_date = None
  for obj in timeboxed_objects:
    if not obj.is_done:
      obj_end_date = obj.end_date
      if isinstance(obj_end_date, datetime):
        obj_end_date = obj_end_date.date()
      if obj_end_date is not None:
        if end_date is None or end_date > obj_end_date:
          end_date = obj_end_date
  return end_date


def _get_date_range(timeboxed_objects):
  start_date = None
  end_date = None

  for obj in timeboxed_objects:
    obj_start_date = obj.start_date
    if isinstance(obj_start_date, datetime):
      obj_start_date = obj_start_date.date()
    obj_end_date = obj.end_date
    if isinstance(obj_end_date, datetime):
      obj_end_date = obj_end_date.date()
    if obj_start_date is not None:
      if start_date is None or start_date > obj_start_date:
        start_date = obj_start_date
    if obj_end_date is not None:
      if end_date is None or end_date < obj_end_date:
        end_date = obj_end_date
  return start_date, end_date


def update_cycle_dates(cycle):
  """ This gets all cycle task groups and tasks associated with a cycle and
  calculates the start and end date for the cycle by aggregating cycle task
  dates to cycle task groups and then cycle task group dates to cycle.

  Args:
    cycle: Cycle for which we want to calculate the start and end dates.

  """
  if cycle.id:
    # If `cycle` is already in the database, then eager load required objects
    cycle = models.Cycle.query.filter_by(
        id=cycle.id
    ).options(
        orm.Load(models.Cycle).joinedload(
            'cycle_task_groups'
        ).joinedload(
            'cycle_task_group_tasks'
        ).load_only(
            "id", "status", "start_date", "end_date"
        ),
        orm.Load(models.Cycle).joinedload(
            'cycle_task_groups'
        ).load_only(
            "id", "status", "start_date", "end_date", "next_due_date",
        ),
    ).one()

  if not cycle.cycle_task_group_object_tasks and \
     cycle.workflow.kind != "Backlog":
    cycle.start_date, cycle.end_date = None, None
    cycle.next_due_date = None
    cycle.is_current = False
    return

  # Don't update cycle and cycle task group dates for backlog workflows
  if cycle.workflow.kind == "Backlog":
    return

  for ctg in cycle.cycle_task_groups:
    ctg.start_date, ctg.end_date = _get_date_range(
        ctg.cycle_task_group_tasks)
    ctg.next_due_date = _get_min_end_date(
        ctg.cycle_task_group_tasks)

  cycle.start_date, cycle.end_date = _get_date_range(cycle.cycle_task_groups)
  cycle.next_due_date = _get_min_next_due_date(cycle.cycle_task_groups)


def build_cycles(workflow, cycle=None, user=None):
  """Build all required cycles for current workflow.

  workflow: Workflow instance (required).
  cycle: Cycle instance (optional). Cycle instance that started at first.
  user: User isntance (optional). User who will be the creator of the cycles.
  """
  user = user or get_current_user()
  if not workflow.next_cycle_start_date:
    workflow.next_cycle_start_date = workflow.calc_next_adjusted_date(
        workflow.min_task_start_date)
  if cycle:
    build_cycle(workflow, cycle, user)
  if workflow.unit and workflow.repeat_every:
    while workflow.next_cycle_start_date <= date.today():
      build_cycle(workflow, current_user=user)


@signals.Restful.model_posted.connect_via(models.Cycle)
def handle_cycle_post(sender, obj=None, src=None, service=None):  # noqa pylint: disable=unused-argument
  if not src.get('autogenerate', False):
    return
  # When called via a REST POST, use current user.
  workflow = obj.workflow
  workflow.status = workflow.ACTIVE
  build_cycles(workflow, obj)


def _create_cycle_task(task_group_task, cycle, cycle_task_group, current_user):
  """Create a cycle task along with relations to other objects"""
  description = models.CycleTaskGroupObjectTask.default_description if \
      task_group_task.object_approval else task_group_task.description

  workflow = cycle.workflow
  start_date = workflow.calc_next_adjusted_date(task_group_task.start_date)
  end_date = workflow.calc_next_adjusted_date(task_group_task.end_date)

  cycle_task_group_object_task = models.CycleTaskGroupObjectTask(
      context=cycle.context,
      cycle=cycle,
      cycle_task_group=cycle_task_group,
      task_group_task=task_group_task,
      title=task_group_task.title,
      description=description,
      sort_index=task_group_task.sort_index,
      start_date=start_date,
      end_date=end_date,
      contact=task_group_task.contact,
      status=models.CycleTaskGroupObjectTask.ASSIGNED,
      modified_by=current_user,
      task_type=task_group_task.task_type,
      response_options=task_group_task.response_options,
  )
  return cycle_task_group_object_task


def create_old_style_cycle(cycle, task_group, cycle_task_group, current_user):
  """ This function preserves the old style of creating cycles, so each object
  gets its own task assigned to it.
  """
  if len(task_group.task_group_objects) == 0:
    for task_group_task in task_group.task_group_tasks:
      cycle_task_group_object_task = _create_cycle_task(
          task_group_task, cycle, cycle_task_group,
          current_user)

  for task_group_object in task_group.task_group_objects:
    object_ = task_group_object.object
    for task_group_task in task_group.task_group_tasks:
      cycle_task_group_object_task = _create_cycle_task(
          task_group_task, cycle, cycle_task_group,
          current_user)
      Relationship(source=cycle_task_group_object_task, destination=object_)


def build_cycle(workflow, cycle=None, current_user=None):
  """Build a cycle with it's child objects"""

  if not workflow.tasks:
    logger.error("Starting a cycle has failed on Workflow with "
                 "slug == '%s' and id == '%s'", workflow.slug, workflow.id)
    pusher.update_or_create_notifications(workflow, date.today(),
                                          "cycle_start_failed")
    return

  # Determine the relevant Workflow
  cycle = cycle or models.Cycle()

  # Use WorkflowOwner role when this is called via the cron job.
  if not current_user:
    for user_role in workflow.context.user_roles:
      if user_role.role.name == "WorkflowOwner":
        current_user = user_role.person
        break
  # Populate the top-level Cycle object
  cycle.workflow = workflow
  cycle.is_current = True
  cycle.context = workflow.context
  cycle.title = workflow.title
  cycle.description = workflow.description
  cycle.is_verification_needed = workflow.is_verification_needed
  cycle.status = models.Cycle.ASSIGNED

  # Populate CycleTaskGroups based on Workflow's TaskGroups
  for task_group in workflow.task_groups:
    cycle_task_group = models.CycleTaskGroup(
        context=cycle.context,
        cycle=cycle,
        task_group=task_group,
        title=task_group.title,
        description=task_group.description,
        end_date=cycle.end_date,
        modified_by=current_user,
        contact=task_group.contact,
        status=models.CycleTaskGroup.ASSIGNED,
        sort_index=task_group.sort_index,
    )

    # preserve the old cycle creation for old workflows, so each object
    # gets its own cycle task
    if workflow.is_old_workflow:
      create_old_style_cycle(cycle, task_group, cycle_task_group, current_user)
    else:
      for task_group_task in task_group.task_group_tasks:
        cycle_task_group_object_task = _create_cycle_task(
            task_group_task, cycle, cycle_task_group, current_user)

        for task_group_object in task_group.task_group_objects:
          object_ = task_group_object.object
          Relationship(source=cycle_task_group_object_task,
                       destination=object_)

  update_cycle_dates(cycle)
  Signals.workflow_cycle_start.send(
      cycle.__class__,
      obj=cycle,
      new_status=cycle.status,
      old_status=None
  )
  workflow.repeat_multiplier += 1
  workflow.next_cycle_start_date = workflow.calc_next_adjusted_date(
      workflow.min_task_start_date)
  return cycle


# 'Finished' and 'Verified' states are determined via these links
_cycle_task_children_attr = {
    models.CycleTaskGroup: ['cycle_task_group_tasks'],
    models.Cycle: ['cycle_task_groups']
}


def update_cycle_task_child_state(obj):
  """Update child attributes state of cycle task

  Args:
    obj: Cycle task instance
  """
  status_order = (None, 'Assigned', 'InProgress',
                  'Declined', 'Finished', 'Verified')
  status = obj.status
  children_attrs = _cycle_task_children_attr.get(type(obj), [])
  for children_attr in children_attrs:
    if children_attr:
      children = getattr(obj, children_attr, None)
      for child in children:
        if status == 'Declined' or \
           status_order.index(status) > status_order.index(child.status):
          if is_allowed_update(child.__class__.__name__,
                               child.id, child.context.id):
            old_status = child.status
            child.status = status
            Signals.status_change.send(
                child.__class__,
                obj=child,
                new_status=child.status,
                old_status=old_status
            )
          update_cycle_task_child_state(child)


def _update_parent_state(parent, child_statuses):
  """Util function, update status of sent parent, if it's allowed.

  New status based on sent object status and sent child_statuses"""
  old_status = parent.status
  if len(child_statuses) == 1:
    new_status = child_statuses.pop()
    if new_status == "Declined":
      new_status = "InProgress"
  elif {"InProgress", "Declined", "Assigned"} & child_statuses:
    new_status = "InProgress"
  else:
    new_status = "Finished"
  if old_status == new_status:
    return
  parent.status = new_status
  Signals.status_change.send(
      parent.__class__,
      obj=parent,
      old_status=old_status,
      new_status=new_status,
  )


def update_cycle_task_object_task_parent_state(obj, is_put=False):
  """Update cycle task group status for sent cycle task"""
  if obj.cycle.workflow.kind == "Backlog":
    return
  if is_put:
    # On CycleTask status change via PUT request new status is not in DB yet,
    # but old status is in DB. They should be swapped.
    child_statuses = set(i[0] for i in db.session.query(
        models.CycleTaskGroupObjectTask.status
    ).filter(
        models.CycleTaskGroupObjectTask.cycle_task_group_id ==
        obj.cycle_task_group_id,
        models.CycleTaskGroupObjectTask.id != obj.id
    ).distinct().with_for_update()) | {obj.status}
  else:
    child_statuses = set(i[0] for i in db.session.query(
        models.CycleTaskGroupObjectTask.status
    ).filter(
        models.CycleTaskGroupObjectTask.cycle_task_group_id ==
        obj.cycle_task_group_id
    ).distinct().with_for_update())
  _update_parent_state(
      obj.cycle_task_group,
      child_statuses
  )
  update_cycle_task_group_parent_state(obj.cycle_task_group)


def update_cycle_task_group_parent_state(obj):  # noqa pylint: disable=invalid-name
  """Update cycle status for sent cycle task group"""
  if obj.cycle.workflow.kind == "Backlog":
    return
  child_statuses = set(i[0] for i in db.session.query(
      models.CycleTaskGroup.status
  ).filter(
      models.CycleTaskGroup.cycle_id == obj.cycle_id,
      models.CycleTaskGroup.id != obj.id
  ).distinct().with_for_update()) | {obj.status}
  _update_parent_state(
      obj.cycle,
      child_statuses
  )


def ensure_assignee_is_workflow_member(obj):  # noqa pylint: disable=invalid-name
  """Checks what role assignee has in the context of
  a workflow. If he has none he gets the Workflow Member role."""
  if not obj.contact:
    return

  if not obj.is_contact_workflow_person:
    obj.workflow.add_workflow_person(obj.contact, 'WorkflowMember')
    return

  if not obj.is_contact_has_wf_user_role:
    obj.workflow.add_user_role(obj.contact, 'WorkflowMember')


def start_end_date_validator(tgt):
  if tgt.start_date > tgt.end_date:
    raise ValueError('End date can not be behind Start date')

  if max(tgt.start_date.isoweekday(),
         tgt.end_date.isoweekday()) > all_models.Workflow.WORK_WEEK_LEN:
    workflow = tgt.task_group.workflow
    if workflow.unit == workflow.DAY_UNIT:
      raise ValueError("Daily tasks cannot be started or stopped on weekend")


def calculate_new_next_cycle_start_date(workflow):  # noqa pylint: disable=invalid-name
  if not workflow.unit or not workflow.repeat_every:
    return
  if workflow.status != workflow.ACTIVE:
    return
  today = date.today()
  min_task_start_date = workflow.min_task_start_date
  workflow.repeat_multiplier = 0
  workflow.next_cycle_start_date = min_task_start_date
  if min_task_start_date is None:
    return
  while not workflow.next_cycle_start_date > today:
    workflow.repeat_multiplier += 1
    workflow.next_cycle_start_date = workflow.calc_next_adjusted_date(
        min_task_start_date)


@signals.Restful.model_put.connect_via(models.TaskGroupTask)
@signals.Restful.model_posted.connect_via(models.TaskGroupTask)
def handle_task_group_task_put_post(sender, obj=None, src=None, service=None):  # noqa pylint: disable=unused-argument
  start_end_date_validator(obj)
  if inspect(obj).attrs.contact.history.has_changes():
    ensure_assignee_is_workflow_member(obj)

  # If relative days were change we must update workflow next cycle start date
  if inspect(obj).attrs.start_date.history.has_changes():
    calculate_new_next_cycle_start_date(obj.task_group.workflow)


@signals.Restful.model_deleted.connect_via(models.TaskGroupTask)
def handle_task_group_task_delete(sender, obj=None, src=None, service=None):  # noqa pylint: disable=unused-argument
  task_group = obj.task_group
  task_group.task_group_tasks = [t for t in task_group.task_group_tasks
                                 if t.id != obj.id]
  calculate_new_next_cycle_start_date(task_group.workflow)


@signals.Restful.model_posted.connect_via(models.TaskGroup)
def handle_task_group_post(sender, obj=None, src=None, service=None):  # noqa pylint: disable=unused-argument
  if src.get('clone'):
    source_task_group_id = src.get('clone')
    source_task_group = models.TaskGroup.query.filter_by(
        id=source_task_group_id
    ).first()
    source_task_group.copy(
        obj,
        clone_people=src.get('clone_people', False),
        clone_tasks=src.get('clone_tasks', False),
        clone_objects=src.get('clone_objects', False)
    )
    obj.title = source_task_group.title + ' (copy ' + str(obj.id) + ')'

  ensure_assignee_is_workflow_member(obj)
  calculate_new_next_cycle_start_date(obj.workflow)


@signals.Restful.model_deleted.connect_via(models.TaskGroup)
def handle_task_group_delete(sender, obj=None, src=None, service=None):  # noqa pylint: disable=unused-argument
  workflow = obj.workflow
  workflow.task_groups = [t for t in obj.workflow.task_groups
                          if t.id != obj.id]
  calculate_new_next_cycle_start_date(workflow)


@signals.Restful.model_put.connect_via(models.TaskGroup)
def handle_task_group_put(sender, obj=None, src=None, service=None):  # noqa pylint: disable=unused-argument
  if inspect(obj).attrs.contact.history.has_changes():
    ensure_assignee_is_workflow_member(obj)
  calculate_new_next_cycle_start_date(obj.workflow)


@signals.Restful.model_deleted.connect_via(models.CycleTaskGroupObjectTask)
def handle_cycle_task_group_object_task_delete(sender, obj=None,  # noqa pylint: disable=invalid-name
                                               src=None, service=None):  # noqa pylint: disable=unused-argument
  """Update cycle dates and statuses"""
  db.session.flush()
  update_cycle_dates(obj.cycle)


@signals.Restful.model_put.connect_via(models.CycleTaskGroupObjectTask)
def handle_cycle_task_group_object_task_put(  # noqa pylint: disable=invalid-name
        sender, obj=None, src=None, service=None):  # noqa pylint: disable=unused-argument

  if inspect(obj).attrs.contact.history.has_changes():
    ensure_assignee_is_workflow_member(obj)

  if any([inspect(obj).attrs.start_date.history.has_changes(),
          inspect(obj).attrs.end_date.history.has_changes()]):
    update_cycle_dates(obj.cycle)

  if inspect(obj).attrs.status.history.has_changes():
    # TODO: check why update_cycle_object_parent_state destroys object history
    # when accepting the only task in a cycle. The listener below is a
    # workaround because of that.
    Signals.status_change.send(
        obj.__class__,
        obj=obj,
        new_status=obj.status,
        old_status=inspect(obj).attrs.status.history.deleted.pop(),
    )
    update_cycle_task_object_task_parent_state(obj, is_put=True)

  # Doing this regardless of status.history.has_changes() is important in order
  # to update objects that have been declined. It updates the os_last_updated
  # date and last_updated_by.
  if getattr(obj.task_group_task, 'object_approval', None):
    for tgobj in obj.task_group_task.task_group.objects:
      if obj.status == 'Verified':
        tgobj.modified_by = get_current_user()
        tgobj.set_reviewed_state()
    db.session.flush()


@signals.Restful.model_posted_after_commit.connect_via(
    models.CycleTaskGroupObjectTask)
@signals.Restful.model_deleted_after_commit.connect_via(
    models.CycleTaskGroupObjectTask)
# noqa pylint: disable=unused-argument
def handle_cycle_object_status(
        sender, obj=None, src=None, service=None, event=None):
  """Calculate status of cycle and cycle task group"""
  update_cycle_task_object_task_parent_state(obj)


@signals.Restful.model_posted.connect_via(models.CycleTaskGroupObjectTask)
def handle_cycle_task_group_object_task_post(  # noqa pylint: disable=invalid-name
        sender, obj=None, src=None, service=None):  # noqa pylint: disable=unused-argument

  if obj.cycle.workflow.kind != "Backlog":
    ensure_assignee_is_workflow_member(obj)
  update_cycle_dates(obj.cycle)

  Signals.status_change.send(
      obj.__class__,
      obj=obj,
      new_status=obj.status,
      old_status=None,
  )
  db.session.flush()


@signals.Restful.model_put.connect_via(models.CycleTaskGroup)
def handle_cycle_task_group_put(
        sender, obj=None, src=None, service=None):  # noqa pylint: disable=unused-argument
  if inspect(obj).attrs.status.history.has_changes():
    update_cycle_task_group_parent_state(obj)
    update_cycle_task_child_state(obj)


def update_workflow_state(workflow):
  if workflow.status == workflow.DRAFT:
    return False
  if any(c.is_current for c in workflow.cycles):
    workflow.status = workflow.ACTIVE
  else:
    workflow.status = workflow.INACTIVE


@signals.Restful.model_put.connect_via(models.Cycle)
def handle_cycle_put(
        sender, obj=None, src=None, service=None):  # noqa pylint: disable=unused-argument
  if inspect(obj).attrs.is_current.history.has_changes():
    update_workflow_state(obj.workflow)

# Check if workflow should be Inactive after recurrence change


def _validate_put_workflow_fields(workflow):
  """Validates Workflow's fields update.

    Args:
        workflow: Workflow class instance.
    Raises:
        ValueError: An error occurred in case of failed validation.
    """
  if (inspect(workflow).attrs.unit.history.has_changes() or
          inspect(workflow).attrs.repeat_every.history.has_changes()):
    raise ValueError("'unit', 'repeat_every' fields are unchangeable")
  if (inspect(workflow).attrs.recurrences.history.has_changes() and
          workflow.recurrences and workflow.unit is None and
          workflow.repeat_every is None):
    raise ValueError("OneTime workflow cannot be recurrent")


# noqa pylint: disable=unused-argument  # noqa pylint: disable=unused-argument
@signals.Restful.model_put.connect_via(models.Workflow)
def handle_workflow_put(sender, obj=None, src=None, service=None):
  _validate_put_workflow_fields(obj)
  if (inspect(obj).attrs.recurrences.history.has_changes() and
          not obj.recurrences):
    update_workflow_state(obj)
    return
  if not inspect(obj).attrs.status.history.has_changes():
    return
  new = inspect(obj).attrs.status.history.added[0]
  old = inspect(obj).attrs.status.history.deleted[-1]
  # first activate wf
  if (old, new) == (obj.DRAFT, obj.ACTIVE):
    # allow only of it has at leask one task_group
    if not obj.task_groups:
      raise ValueError("Workflow with no Task Groups can not be activated.")
    build_cycles(obj)


# noqa pylint: disable=unused-argument
@signals.Restful.model_posted.connect_via(models.CycleTaskEntry)
def handle_cycle_task_entry_post(sender, obj=None, src=None, service=None):
  if src['is_declining_review'] == '1':
    task = obj.cycle_task_group_object_task
    task.status = task.DECLINED
  else:
    src['is_declining_review'] = 0


# noqa pylint: disable=unused-argument
@Signals.status_change.connect_via(models.Cycle)
def handle_cycle_status_change(sender, obj=None, new_status=None,
                               old_status=None):
  if inspect(obj).attrs.status.history.has_changes():
    obj.is_current = not obj.is_done
    update_workflow_state(obj.workflow)


# noqa pylint: disable=unused-argument
@Signals.status_change.connect_via(models.CycleTaskGroupObjectTask)
def handle_cycle_task_status_change(sender, obj=None, new_status=None,
                                    old_status=None):
  if inspect(obj).attrs.status.history.has_changes():
    if new_status == obj.VERIFIED:
      obj.verified_date = datetime.now()
    elif new_status == obj.FINISHED:
      obj.finished_date = datetime.now()
      obj.verified_date = None
    else:
      obj.finished_date = None
      obj.verified_date = None


def _find_role(role_name):
  """Find role by its name.

  Args:
      role_name: User role name.
  Returns:
      Role instance.
  """
  return db.session.query(Role).filter(Role.name == role_name).first()


# noqa pylint: disable=unused-argument
@signals.Restful.model_posted.connect_via(models.WorkflowPerson)
def handle_workflow_person_post(sender, obj=None, src=None, service=None):
  # add a user_roles mapping assigning the user creating the workflow
  # the WorkflowOwner role in the workflow's context.
  UserRole(
      person=obj.person,
      role=_find_role('WorkflowMember'),
      context=obj.context,
      modified_by=get_current_user(),
  )


def _validate_post_workflow_fields(workflow):
  """Validates Workflow's 'repeat_every' and 'unit' fields dependency.

  Validates that Workflow's 'repeat_every' and 'unit' fields can have NULL
  only simultaneously.

  Args:
      workflow: Workflow class instance.
  Raises:
      ValueError: An error occurred in case of failed dependency validation.
  """
  if ((workflow.repeat_every is None and workflow.unit is not None) or
          (workflow.repeat_every is not None and workflow.unit is None)):
    raise ValueError("Workflow 'repeat_every' and 'unit' fields "
                     "can be NULL only simultaneously")


# noqa pylint: disable=unused-argument
@signals.Restful.model_posted.connect_via(models.Workflow)
def handle_workflow_post(sender, obj=None, src=None, service=None):
  _validate_post_workflow_fields(obj)

  source_workflow = None

  if src.get('clone'):
    source_workflow_id = src.get('clone')
    source_workflow = models.Workflow.query.filter_by(
        id=source_workflow_id
    ).first()
    source_workflow.copy(obj)
    db.session.add(obj)
    db.session.flush()
    obj.title = source_workflow.title + ' (copy ' + str(obj.id) + ')'

  db.session.flush()
  # get the personal context for this logged in user
  current_user = get_current_user()
  personal_context = current_user.get_or_create_object_context(context=1)
  context = obj.get_or_create_object_context(personal_context)
  obj.context = context
  db.session.add(personal_context)
  db.session.add(context)
  db.session.add(obj)
  db.session.flush()

  if not obj.workflow_people:
    # add a user_roles mapping assigning the user creating the workflow
    # the WorkflowOwner role in the workflow's context.
    workflow_owner_role = _find_role('WorkflowOwner')
    user_role = UserRole(
        person=current_user,
        role=workflow_owner_role,
        context=context,
        modified_by=current_user,
    )
    db.session.add(models.WorkflowPerson(
        person=current_user,
        workflow=obj,
        context=context,
        modified_by=current_user,
    ))
    # pass along a temporary attribute for logging the events.
    user_role._display_related_title = obj.title
    db.session.add(user_role)
    db.session.flush()

  # Create the context implication for Workflow roles to default context
  db.session.add(ContextImplication(
      source_context=context,
      context=None,
      source_context_scope='Workflow',
      context_scope=None,
      modified_by=current_user,
  ))

  if not src.get('private'):
    # Add role implication - all users can read a public workflow
    add_public_workflow_context_implication(context)

  if src.get('clone'):
    source_workflow.copy_task_groups(
        obj,
        clone_people=src.get('clone_people', False),
        clone_tasks=src.get('clone_tasks', False),
        clone_objects=src.get('clone_objects', False)
    )

    if src.get('clone_people'):
      workflow_member_role = _find_role('WorkflowMember')
      for authorization in source_workflow.context.user_roles:
        # Current user has already been added as workflow owner
        if authorization.person != current_user:
          db.session.add(UserRole(
              person=authorization.person,
              role=workflow_member_role,
              context=context,
              modified_by=current_user))
      for person in source_workflow.people:
        if person != current_user:
          db.session.add(models.WorkflowPerson(
              person=person,
              workflow=obj,
              context=context))


def add_public_workflow_context_implication(context, check_exists=False):
  if check_exists and db.session.query(ContextImplication).filter(
      and_(ContextImplication.context_id == context.id,
           ContextImplication.source_context_id == None)).count() > 0:  # noqa
    return
  db.session.add(ContextImplication(
      source_context=None,
      context=context,
      source_context_scope=None,
      context_scope='Workflow',
      modified_by=get_current_user(),
  ))


def init_extra_views(app):
  from . import views
  views.init_extra_views(app)


def start_recurring_cycles():
  today = date.today()
  workflows = models.Workflow.query.filter(
      models.Workflow.next_cycle_start_date <= today,
      models.Workflow.recurrences == True  # noqa
  )
  for workflow in workflows:
    # Follow same steps as in model_posted.connect_via(models.Cycle)
    while workflow.next_cycle_start_date <= date.today():
      cycle = build_cycle(workflow)
      if not cycle:
        break
      db.session.add(cycle)
      notification.handle_cycle_created(cycle, False)
      notification.handle_workflow_modify(None, workflow)
  log_event(db.session)
  db.session.commit()


class WorkflowRoleContributions(RoleContributions):
  contributions = {
      'ProgramCreator': {
          'read': ['Workflow'],
          'create': ['Workflow'],
      },
      'Creator': {
          'create': ['Workflow', 'CycleTaskGroupObjectTask']
      },
      'Editor': {
          'read': ['Workflow', 'CycleTaskGroupObjectTask'],
          'create': ['Workflow', 'CycleTaskGroupObjectTask'],
          'update': ['CycleTaskGroupObjectTask'],
          'edit': ['CycleTaskGroupObjectTask'],
      },
      'Reader': {
          'read': ['Workflow', 'CycleTaskGroupObjectTask'],
          'create': ['Workflow', 'CycleTaskGroupObjectTask'],
      },
      'ProgramEditor': {
          'read': ['Workflow'],
          'create': ['Workflow'],
      },
      'ProgramOwner': {
          'read': ['Workflow'],
          'create': ['Workflow'],
      },
  }


class WorkflowRoleDeclarations(RoleDeclarations):

  def roles(self):
    return {
        'WorkflowOwner': WorkflowOwner,
        'WorkflowEditor': WorkflowEditor,
        'WorkflowMember': WorkflowMember,
        'BasicWorkflowReader': BasicWorkflowReader,
        'WorkflowBasicReader': WorkflowBasicReader,
    }


class WorkflowRoleImplications(DeclarativeRoleImplications):
  # (Source Context Type, Context Type)
  #   -> Source Role -> Implied Role for Context
  implications = {
      (None, 'Workflow'): {
          'ProgramCreator': ['BasicWorkflowReader'],
          'Editor': ['WorkflowEditor'],
          'Reader': ['BasicWorkflowReader'],
          'Creator': ['WorkflowBasicReader'],
      },
      ('Workflow', None): {
          'WorkflowOwner': ['WorkflowBasicReader'],
          'WorkflowMember': ['WorkflowBasicReader'],
          'WorkflowEditor': ['WorkflowBasicReader'],
      },
  }


ROLE_CONTRIBUTIONS = WorkflowRoleContributions()
ROLE_DECLARATIONS = WorkflowRoleDeclarations()
ROLE_IMPLICATIONS = WorkflowRoleImplications()

contributed_notifications = notification.contributed_notifications
contributed_importables = IMPORTABLE
contributed_exportables = EXPORTABLE
contributed_column_handlers = COLUMN_HANDLERS
contributed_get_ids_related_to = relationship_helper.get_ids_related_to
CONTRIBUTED_CRON_JOBS = [start_recurring_cycles]
NOTIFICATION_LISTENERS = [notification.register_listeners]
