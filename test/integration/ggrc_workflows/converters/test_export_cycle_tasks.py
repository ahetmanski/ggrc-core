# Copyright (C) 2017 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>


"""Tests for task group task specific export."""

from collections import defaultdict

from ddt import data, unpack, ddt

from integration.ggrc_workflows.models import factories
from integration.ggrc.models.factories import PersonFactory
from integration.ggrc import TestCase

from ggrc.models.all_models import CycleTaskGroupObjectTask


@ddt
class TestExportTasks(TestCase):
  """Test imports for basic workflow objects."""

  def setUp(self):
    super(TestExportTasks, self).setUp()
    self.client.get("/login")
    self.headers = {
        'Content-Type': 'application/json',
        "X-Requested-By": "GGRC",
        "X-export-view": "blocks",
    }

  @staticmethod
  def generate_tasks_for_cycle(cycle_count, task_count):
    """generate seceted number of cycles and tasks"""
    results = {}
    for _ in range(cycle_count):
      workflow = factories.WorkflowFactory()
      cycle = factories.CycleFactory(workflow=workflow)
      person = PersonFactory(name="user for cycle {}".format(cycle.id))
      task_group = factories.TaskGroupFactory(workflow=workflow)
      for _ in range(task_count):
        task_group_task = factories.TaskGroupTaskFactory(
            task_group=task_group, contact=person)
        cycle_task_group = factories.CycleTaskGroupFactory(
            cycle=cycle, contact=person)
        task = factories.CycleTaskFactory(cycle=cycle,
                                          cycle_task_group=cycle_task_group,
                                          contact=person,
                                          task_group_task=task_group_task)
        results[task.id] = cycle.slug
    return results

  # pylint: disable=invalid-name
  def assertCycles(self, field, value, cycle_slugs):
    """assertion for search cycles for selected fields and values"""
    search_request = [{
        "object_name": "Cycle",
        "filters": {
            "expression": {
                "left": field,
                "op": {"name": "="},
                "right": value,
            },
        },
        "fields": ["slug"],
    }]
    parsed_data = self.export_parsed_csv(search_request)["Cycle"]
    self.assertEqual(sorted(cycle_slugs),
                     sorted([i["Code*"] for i in parsed_data]))
    self.assertEqual(len(cycle_slugs), len(parsed_data))

  @data(
      #  (Cycle count, tasks in cycle)
      (0, 0),
      (1, 1),
      (2, 1),
      (2, 1),
      (2, 2),
  )
  @unpack
  def test_filter_by_task_title(self, cycle_count, task_count):
    """Test filter cycles by task slug and title"""
    task_cycle_filter = self.generate_tasks_for_cycle(cycle_count, task_count)
    self.assertEqual(bool(cycle_count), bool(task_cycle_filter))
    for task_id, slug in task_cycle_filter.iteritems():
      task = CycleTaskGroupObjectTask.query.filter(
          CycleTaskGroupObjectTask.id == task_id
      ).one()
      self.assertCycles("task title", task.title, [slug])

  @data(
      #  (Cycle count, tasks in cycle)
      (0, 0),
      (1, 1),
      (2, 1),
      (2, 1),
      (2, 2),
  )
  @unpack
  def test_filter_group_title(self, cycle_count, task_count):
    """Test filter cycles by group slug and title"""
    task_cycle_filter = self.generate_tasks_for_cycle(cycle_count, task_count)
    self.assertEqual(bool(cycle_count), bool(task_cycle_filter))
    for task_id, slug in task_cycle_filter.iteritems():
      task = CycleTaskGroupObjectTask.query.filter(
          CycleTaskGroupObjectTask.id == task_id
      ).one()
      self.assertCycles("group title", task.cycle_task_group.title, [slug])

  @data(
      #  (Cycle count, tasks in cycle)
      (0, 0),
      (1, 1),
      (2, 1),
      (2, 1),
      (2, 2),
  )
  @unpack
  def test_filter_by_task_due_date(self, cycle_count, task_count):
    """Test filter cycles by task due date"""
    task_cycle_filter = self.generate_tasks_for_cycle(cycle_count, task_count)
    self.assertEqual(bool(cycle_count), bool(task_cycle_filter))
    due_date_dict = defaultdict(set)
    for task_id, slug in task_cycle_filter.iteritems():
      task = CycleTaskGroupObjectTask.query.filter(
          CycleTaskGroupObjectTask.id == task_id
      ).one()
      due_date_dict[str(task.end_date)].add(slug)

    for due_date, cycle_slugs in due_date_dict.iteritems():
      self.assertCycles("task due date", due_date, list(cycle_slugs))

  @data(
      #  (Cycle count, tasks in cycle)
      (0, 0),
      (1, 1),
      (2, 1),
      (2, 1),
      (2, 2),
  )
  @unpack
  def test_filter_by_group_due_date(self, cycle_count, task_count):
    """Test filter cycles by group due date"""
    task_cycle_filter = self.generate_tasks_for_cycle(cycle_count, task_count)
    self.assertEqual(bool(cycle_count), bool(task_cycle_filter))
    due_date_dict = defaultdict(set)
    for task_id, slug in task_cycle_filter.iteritems():
      task = CycleTaskGroupObjectTask.query.filter(
          CycleTaskGroupObjectTask.id == task_id
      ).one()
      due_date_dict[str(task.cycle_task_group.next_due_date)].add(slug)

    for due_date, cycle_slugs in due_date_dict.iteritems():
      self.assertCycles("group due date", due_date, list(cycle_slugs))

  @data(
      #  (Cycle count, tasks in cycle)
      (0, 0),
      (1, 1),
      (2, 1),
      (2, 1),
      (2, 2),
  )
  @unpack
  def test_filter_by_group_assignee(self, cycle_count, task_count):
    """Test filter cycles by group assignee name or email"""
    task_cycle_filter = self.generate_tasks_for_cycle(cycle_count, task_count)
    self.assertEqual(bool(cycle_count), bool(task_cycle_filter))
    for task_id, slug in task_cycle_filter.iteritems():
      task = CycleTaskGroupObjectTask.query.filter(
          CycleTaskGroupObjectTask.id == task_id
      ).one()
      self.assertCycles(
          "group assignee", task.cycle_task_group.contact.email, [slug])
      self.assertCycles(
          "group assignee", task.cycle_task_group.contact.name, [slug])

  @data(
      #  (Cycle count, tasks in cycle)
      (0, 0),
      (1, 1),
      (2, 1),
      (2, 1),
      (2, 2),
  )
  @unpack
  def test_filter_by_task_assignee(self, cycle_count, task_count):
    """Test filter cycles by task assignee name or email"""
    task_cycle_filter = self.generate_tasks_for_cycle(cycle_count, task_count)
    self.assertEqual(bool(cycle_count), bool(task_cycle_filter))
    for task_id, slug in task_cycle_filter.iteritems():
      task = CycleTaskGroupObjectTask.query.filter(
          CycleTaskGroupObjectTask.id == task_id
      ).one()
      self.assertCycles("task assignee", task.contact.email, [slug])
      self.assertCycles("task assignee", task.contact.name, [slug])

  @data(
      #  (Cycle count, tasks in cycle)
      (0, 0),
      (1, 1),
      (2, 1),
      (2, 1),
      (2, 2),
  )
  @unpack
  def test_filter_by_task_due_date_year(self, cycle_count, task_count):
    """Test filter cycles by task due date year"""
    task_cycle_filter = self.generate_tasks_for_cycle(cycle_count, task_count)
    self.assertEqual(bool(cycle_count), bool(task_cycle_filter))
    due_date_dict = defaultdict(set)
    for task_id, slug in task_cycle_filter.iteritems():
      task = CycleTaskGroupObjectTask.query.filter(
          CycleTaskGroupObjectTask.id == task_id
      ).one()
      key = (task.end_date.year, task.end_date.month, task.end_date.day)
      due_date_dict[key].add(slug)

    for due_date, cycle_slugs in due_date_dict.iteritems():
      self.assertCycles("task due date",
                        "{}-{}-{}".format(*due_date),
                        list(cycle_slugs))

  @data(
      #  (Cycle count, tasks in cycle)
      (0, 0),
      (1, 1),
      (2, 1),
      (2, 1),
      (2, 2),
  )
  @unpack
  def test_filter_by_task_due_date_year_month(self, cycle_count, task_count):
    """Test filter cycles by task due date year month"""
    task_cycle_filter = self.generate_tasks_for_cycle(cycle_count, task_count)
    self.assertEqual(bool(cycle_count), bool(task_cycle_filter))
    due_date_dict = defaultdict(set)
    for task_id, slug in task_cycle_filter.iteritems():
      task = CycleTaskGroupObjectTask.query.filter(
          CycleTaskGroupObjectTask.id == task_id
      ).one()
      due_date_dict[(task.end_date.year, task.end_date.month)].add(slug)

    for due_date, cycle_slugs in due_date_dict.iteritems():
      self.assertCycles("task due date",
                        "{}-{}".format(*due_date),
                        list(cycle_slugs))
