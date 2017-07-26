# Copyright (C) 2017 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
"""Contains functions for next cycle dates calculations"""
from dateutil import relativedelta
from ggrc_workflows.services.workflow_cycle_calculator import google_holidays


def get_setup_cycle_start_date(workflow):
  """Fetches non adjusted setup cycle start date based on TGT user's setup.

  Args:
      workflow: Workflow instance.

  Returns:
      Date when first cycle should be started based on user's setup.
  """
  tgt_start_dates = [
    task.start_date for task_group in workflow.task_groups
    for task in task_group.task_group_tasks
  ]
  return min(tgt_start_dates)


def calc_next_cycle_start_date(workflow, setup_cycle_start_date=None):
  """Calculates next cycle start date.

  Args:
      workflow: Workflow instance.

  Returns:
      Date when next cycle should be started.
  """
  if not setup_cycle_start_date:
    setup_cycle_start_date = get_setup_cycle_start_date(workflow)
  return calc_next_adjusted_date(workflow, setup_cycle_start_date)


def calc_next_cycle_task_dates(workflow, task):
  """Calculates dates which are expected in next cycle.

  Args:
      workflow: Workflow instance.
      task: TaskGroupTask instance which belongs to workflow.

  Returns:
      Adjusted dates which are expected for CycleTask in next cycle.
  """
  return (calc_next_adjusted_date(workflow, task.start_date),
          calc_next_adjusted_date(workflow, task.end_date))


def calc_next_adjusted_date(workflow, setup_date):
  """Calculates adjusted date which are expected in next cycle.

  Args:
      workflow: Workflow instance.
      setup_date: Date which was setup by user.

  Returns:
      Adjusted date which are expected to be in next Workflow cycle.
  """
  def adjust_date(ddate):
    """Adjusts date according the required rule.

    If date is weekend or Google's US holiday, then date should be moved to
    day before until we get working day.

    Args:
        ddate: Date object that should be adjusted.

    Returns:
        Adjusted Date object.
    """
    while ddate.isoweekday() > 5 or ddate in google_holidays.GoogleHolidays():
      ddate -= relativedelta.relativedelta(days=1)
    return ddate
  if workflow.unit == 'week':
    repeat_delta = relativedelta.relativedelta(
        weeks=workflow.repeat_every * workflow.repeat_multiplier)
  elif workflow.unit == 'month':
    repeat_delta = relativedelta.relativedelta(
        months=workflow.repeat_every * workflow.repeat_multiplier)
  else:
    repeat_delta = relativedelta.relativedelta(
        days=workflow.repeat_every * workflow.repeat_multiplier)
  calc_date = setup_date + repeat_delta
  if workflow.unit == 'month' and setup_date.day != calc_date.day:
    calc_date -= relativedelta.relativedelta(calc_date.day)
  return adjust_date(calc_date)
