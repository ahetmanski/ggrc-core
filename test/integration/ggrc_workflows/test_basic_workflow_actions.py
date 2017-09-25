# Copyright (C) 2017 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
"""
Tests for the basic Workflows logic and actions
"""
# pylint: disable=invalid-name

import datetime as dtm
from freezegun import freeze_time

import ddt

from ggrc import db
from ggrc_workflows import start_recurring_cycles
from ggrc_workflows.models import Cycle
from ggrc_workflows.models import CycleTaskGroupObjectTask
from ggrc_workflows.models import TaskGroup
from ggrc_workflows.models import TaskGroupTask
from ggrc_workflows.models import Workflow
from integration.ggrc import TestCase
from integration.ggrc_workflows.generator import WorkflowsGenerator
from integration.ggrc_workflows.models import factories as wf_factories
from integration.ggrc.api_helper import Api
from integration.ggrc.generator import ObjectGenerator
from integration.ggrc.models import factories


@ddt.ddt
class TestWorkflowsCycleGeneration(TestCase):
  """
  Tests for Cycle generation logic
  """
  def setUp(self):
    super(TestWorkflowsCycleGeneration, self).setUp()
    self.api = Api()
    self.generator = WorkflowsGenerator()
    self.object_generator = ObjectGenerator()

  def tearDown(self):
    pass

  def test_recurring_without_tgts_skip(self):
    """Test that Active Workflow without TGTs is skipped on cron job"""
    with freeze_time(dtm.date(2017, 9, 25)):
      with factories.single_commit():
        workflow = wf_factories.WorkflowFactory(repeat_every=1,
                                                unit=Workflow.MONTH_UNIT)
        workflow_id = workflow.id
        group = wf_factories.TaskGroupFactory(workflow=workflow)
        wf_factories.TaskGroupTaskFactory(
            task_group=group,
            start_date=dtm.date(2017, 9, 26),
            end_date=dtm.date(2017, 9, 26) + dtm.timedelta(days=4))
      self.generator.activate_workflow(workflow)
      active_wf = db.session.query(Workflow).filter(
          Workflow.id == workflow_id).one()
      self.assertEqual(active_wf.next_cycle_start_date, dtm.date(2017, 9, 26))
      self.assertEqual(active_wf.recurrences, True)
      self.assertEqual(len(active_wf.cycles), 0)
      TaskGroupTask.query.delete()
      db.session.commit()

    with freeze_time(dtm.date(2017, 10, 25)):
      start_recurring_cycles()
      active_wf = db.session.query(Workflow).filter(
          Workflow.id == workflow_id).one()
      self.assertEqual(active_wf.next_cycle_start_date, dtm.date(2017, 9, 26))
      self.assertEqual(active_wf.recurrences, True)
      self.assertEqual(len(active_wf.cycles), 0)

  @ddt.data(
      # (expected, setup_date),
      (dtm.date(2017, 2, 28), dtm.date(2017, 2, 28)),
      (dtm.date(2017, 3, 3), dtm.date(2017, 3, 3)),
      (dtm.date(2017, 8, 4), dtm.date(2017, 8, 5)),
      (dtm.date(2017, 7, 21), dtm.date(2017, 7, 22)),
  )
  @ddt.unpack
  def test_one_time_wf_start_date_shifting(self, expected, setup_date):
    """Test case for correct cycle task start_ dates for one_time wf"""
    with factories.single_commit():
      workflow = wf_factories.WorkflowFactory()
      group = wf_factories.TaskGroupFactory(workflow=workflow)
      wf_factories.TaskGroupTaskFactory(
          task_group=group,
          start_date=setup_date,
          end_date=setup_date + dtm.timedelta(days=4))
    self.generator.generate_cycle(workflow)
    self.generator.activate_workflow(workflow)
    active_wf = db.session.query(Workflow).filter(
        Workflow.status == 'Active').one()
    self.assertEqual(1,
                     len(active_wf.cycles[0].cycle_task_group_object_tasks))
    cycle_task = active_wf.cycles[0].cycle_task_group_object_tasks[0]
    adj_start_date = cycle_task.start_date
    self.assertEqual(expected, adj_start_date)

  @ddt.data(
      # (expected, end_date),
      (dtm.date(2017, 2, 28), dtm.date(2017, 2, 28)),
      (dtm.date(2017, 3, 3), dtm.date(2017, 3, 3)),
      (dtm.date(2017, 8, 4), dtm.date(2017, 8, 5)),
      (dtm.date(2017, 7, 21), dtm.date(2017, 7, 22)),
  )
  @ddt.unpack
  def test_one_time_wf_end_date_shifting(self, expected, setup_date):
    """Test case for correct cycle task end_ dates for one_time wf"""
    with factories.single_commit():
      workflow = wf_factories.WorkflowFactory()
      group = wf_factories.TaskGroupFactory(workflow=workflow)
      wf_factories.TaskGroupTaskFactory(
          task_group=group,
          start_date=setup_date - dtm.timedelta(days=4),
          end_date=setup_date)
    self.generator.generate_cycle(workflow)
    self.generator.activate_workflow(workflow)
    active_wf = db.session.query(Workflow).filter(
        Workflow.status == 'Active').one()
    self.assertEqual(1,
                     len(active_wf.cycles[0].cycle_task_group_object_tasks))
    cycle_task = active_wf.cycles[0].cycle_task_group_object_tasks[0]
    adj_end_date = cycle_task.end_date
    self.assertEqual(expected, adj_end_date)

  # pylint: disable=too-many-arguments
  @ddt.data(
      # (expected, setup_date, freeze_date, repeat_every, unit),
      (dtm.date(2017, 3, 28), dtm.date(2017, 2, 28), dtm.date(2017, 4, 28), 1,
       Workflow.MONTH_UNIT),
      (dtm.date(2017, 2, 28), dtm.date(2017, 1, 31), dtm.date(2017, 3, 31), 1,
       Workflow.MONTH_UNIT),
      (dtm.date(2017, 3, 17), dtm.date(2017, 3, 10), dtm.date(2017, 3, 24), 1,
       Workflow.WEEK_UNIT),
      (dtm.date(2017, 2, 28), dtm.date(2016, 2, 29), dtm.date(2017, 3, 29), 12,
       Workflow.MONTH_UNIT),
      (dtm.date(2017, 4, 28), dtm.date(2017, 1, 31), dtm.date(2017, 5, 31), 3,
       Workflow.MONTH_UNIT),
  )
  @ddt.unpack
  def test_recurring_wf_start_date_shifting(self, expected, setup_date,
                                            freeze_date, repeat_every, unit):
    """Test case for correct next cycle task start_date for recurring wf"""
    with freeze_time(freeze_date):
      with factories.single_commit():
        workflow = wf_factories.WorkflowFactory(repeat_every=repeat_every,
                                                unit=unit)
        group = wf_factories.TaskGroupFactory(workflow=workflow)
        wf_factories.TaskGroupTaskFactory(
            task_group=group,
            start_date=setup_date,
            end_date=setup_date + dtm.timedelta(days=4))
      self.generator.activate_workflow(workflow)

    active_wf = db.session.query(Workflow).filter(
        Workflow.status == 'Active').one()
    cycle_task = active_wf.cycles[1].cycle_task_group_object_tasks[0]
    adj_start_date = cycle_task.start_date
    self.assertEqual(expected, adj_start_date)

  @ddt.data(
      # today is dtm.date(2017, 8, 15), task repeat every
      # (setup_start_date, update_start_date, expected_date),
      (dtm.date(2017, 1, 15), dtm.date(2017, 1, 1), dtm.date(2017, 9, 1)),
      (dtm.date(2017, 1, 15), dtm.date(2017, 1, 5), dtm.date(2017, 9, 5)),
      # new cycle starts on weekend that's why it moves to friday
      (dtm.date(2017, 1, 15), dtm.date(2017, 1, 10), dtm.date(2017, 9, 8)),
      (dtm.date(2017, 1, 15), dtm.date(2017, 8, 15), dtm.date(2017, 9, 15)),
      # new cycle starts on weekend that's why it moves to friday
      (dtm.date(2017, 1, 15), dtm.date(2017, 1, 20), dtm.date(2017, 8, 18)),
      (dtm.date(2017, 1, 15), dtm.date(2017, 1, 25), dtm.date(2017, 8, 25)),
      (dtm.date(2017, 8, 16), dtm.date(2017, 8, 14), dtm.date(2017, 9, 14)),
      (dtm.date(2017, 8, 16), dtm.date(2017, 8, 18), dtm.date(2017, 8, 18)),
      (dtm.date(2017, 8, 14), dtm.date(2017, 8, 18), dtm.date(2017, 8, 18)),
  )
  @ddt.unpack
  def test_recalculate_date(self,
                            setup_start_date,
                            update_start_date,
                            expected_date):
    """Recalculate next cycle start date"""
    with freeze_time(dtm.date(2017, 8, 15)):
      with factories.single_commit():
        workflow = wf_factories.WorkflowFactory(repeat_every=1,
                                                status=Workflow.DRAFT,
                                                unit=Workflow.MONTH_UNIT)
        group = wf_factories.TaskGroupFactory(workflow=workflow)
        task_id = wf_factories.TaskGroupTaskFactory(
            task_group=group,
            start_date=setup_start_date,
            end_date=setup_start_date + dtm.timedelta(days=4)).id
      self.generator.activate_workflow(workflow)
      self.api.put(TaskGroupTask.query.get(task_id),
                   {"start_date": update_start_date,
                    "end_date": update_start_date + dtm.timedelta(4)})
    active_wf = db.session.query(Workflow).filter(
        Workflow.status == 'Active').one()
    self.assertEqual(expected_date, active_wf.next_cycle_start_date)

  def test_recalculate_date_not_started(self):
    """Changing start_date on notstarted workflow will
       not affect next_cycle_start_date"""
    setup_start_date = dtm.date(2017, 1, 15)
    update_start_date = dtm.date(2017, 1, 1)
    with freeze_time(dtm.date(2017, 8, 15)):
      with factories.single_commit():
        workflow = wf_factories.WorkflowFactory(repeat_every=1,
                                                status=Workflow.DRAFT,
                                                unit=Workflow.MONTH_UNIT)
        group = wf_factories.TaskGroupFactory(workflow=workflow)
        task_id = wf_factories.TaskGroupTaskFactory(
            task_group=group,
            start_date=setup_start_date,
            end_date=setup_start_date + dtm.timedelta(days=4)).id
        workflow_id = workflow.id
    self.api.put(TaskGroupTask.query.get(task_id),
                 {"start_date": update_start_date,
                  "end_date": update_start_date + dtm.timedelta(4)})
    self.assertIsNone(Workflow.query.get(workflow_id).next_cycle_start_date)

  @ddt.data(
      # (setup_date, freeze_date, repeat_every, unit),
      (dtm.date(2017, 2, 28), dtm.date(2017, 4, 28), 1, Workflow.MONTH_UNIT),
      (dtm.date(2017, 3, 10), dtm.date(2017, 3, 24), 1, Workflow.WEEK_UNIT),
  )
  @ddt.unpack
  def test_recurring_wf_start_date_and_cycles(self, setup_date, freeze_date,
                                              repeat_every, unit):
    """Test case for correct cycle start date and number of cycles"""
    with freeze_time(freeze_date):
      with factories.single_commit():
        workflow = wf_factories.WorkflowFactory(repeat_every=repeat_every,
                                                unit=unit)
        group = wf_factories.TaskGroupFactory(workflow=workflow)
        wf_factories.TaskGroupTaskFactory(
            task_group=group,
            start_date=setup_date,
            end_date=setup_date + dtm.timedelta(days=4))
      self.generator.activate_workflow(workflow)

    active_wf = db.session.query(Workflow).filter(
        Workflow.status == 'Active').one()
    # freeze_date is chosen so that we expect 3 cycles to be generated:
    self.assertEqual(len(active_wf.cycles), 3)
    cycle_task = active_wf.cycles[0].cycle_task_group_object_tasks[0]
    adj_start_date = cycle_task.start_date
    self.assertEqual(setup_date, adj_start_date)

  @ddt.data(
      # (setup_date, freeze_date, repeat_every, unit,
      #  exp_start_date, exp_end_date),
      (dtm.date(2017, 2, 28), dtm.date(2017, 4, 28), 1, Workflow.MONTH_UNIT,
       dtm.date(2017, 2, 27), dtm.date(2017, 3, 3)),
      (dtm.date(2017, 3, 10), dtm.date(2017, 3, 24), 1, Workflow.WEEK_UNIT,
       dtm.date(2017, 3, 9), dtm.date(2017, 3, 14)),
  )
  @ddt.unpack
  def test_recurring_wf_start_end_cycle_dates(self,
                                              setup_date,
                                              freeze_date,
                                              repeat_every,
                                              unit,
                                              exp_start_date,
                                              exp_end_date):
    """Test case for correct cycle start and end dates"""
    with freeze_time(freeze_date):
      with factories.single_commit():
        workflow = wf_factories.WorkflowFactory(repeat_every=repeat_every,
                                                unit=unit)
        group = wf_factories.TaskGroupFactory(workflow=workflow)
        wf_factories.TaskGroupTaskFactory(
            task_group=group,
            start_date=setup_date,
            end_date=setup_date + dtm.timedelta(days=4))
        wf_factories.TaskGroupTaskFactory(
            task_group=group,
            start_date=setup_date - dtm.timedelta(days=1),
            end_date=setup_date + dtm.timedelta(days=3))
      self.generator.activate_workflow(workflow)

    active_wf = db.session.query(Workflow).filter(
        Workflow.status == 'Active').one()
    # freeze_date is chosen so that we expect 3 cycles to be generated:
    self.assertEqual(len(active_wf.cycles), 3)
    cycle = active_wf.cycles[0]
    self.assertEqual(cycle.start_date, exp_start_date)
    self.assertEqual(cycle.end_date, exp_end_date)

  @ddt.data(
      # (setup_date, freeze_date, repeat_every, unit),
      (dtm.date(2017, 4, 28), dtm.date(2017, 2, 28), 1, Workflow.MONTH_UNIT),
      (dtm.date(2017, 3, 5), dtm.date(2017, 3, 3), 1, Workflow.DAY_UNIT),
      (dtm.date(2017, 3, 24), dtm.date(2017, 3, 10), 1, Workflow.WEEK_UNIT),
  )
  @ddt.unpack
  def test_recurring_wf_future_start_date(self, setup_date, freeze_date,
                                          repeat_every, unit):
    """Test case for 0 number of cycles for future setup date"""
    with freeze_time(freeze_date):
      with factories.single_commit():
        workflow = wf_factories.WorkflowFactory(repeat_every=repeat_every,
                                                unit=unit)
        group = wf_factories.TaskGroupFactory(workflow=workflow)
        wf_factories.TaskGroupTaskFactory(
            task_group=group,
            start_date=setup_date,
            end_date=setup_date + dtm.timedelta(days=4))
      self.generator.activate_workflow(workflow)

    active_wf = db.session.query(Workflow).filter(
        Workflow.status == 'Active').one()
    # no cycles should be generated:
    self.assertEqual(len(active_wf.cycles), 0)

  @ddt.data(
      # (expected_date, expected_num, setup_date,
      #  freeze_date, repeat_every),
      # should not exclude Jul 4
      (dtm.date(2017, 1, 2), 2, dtm.date(2016, 12, 30),
       dtm.date(2017, 1, 2), 1),
      (dtm.date(2017, 1, 4), 2, dtm.date(2016, 12, 30),
       dtm.date(2017, 1, 8), 3),
      (dtm.date(2017, 7, 7), 5, dtm.date(2017, 7, 3),
       dtm.date(2017, 7, 8), 1),
      (dtm.date(2017, 7, 11), 3, dtm.date(2017, 7, 3),
       dtm.date(2017, 7, 12), 3),
      (dtm.date(2017, 7, 10), 2, dtm.date(2017, 7, 3),
       dtm.date(2017, 7, 11), 5),
      (dtm.date(2017, 7, 12), 2, dtm.date(2017, 7, 3),
       dtm.date(2017, 7, 20), 7),
      (dtm.date(2017, 7, 13), 2, dtm.date(2017, 6, 1),
       dtm.date(2017, 7, 31), 30),
  )
  @ddt.unpack
  def test_recurring_daily_workflow_dates(self,
                                          expected_date,
                                          expected_num,
                                          setup_date,
                                          freeze_date,
                                          repeat_every):
    """
    Test for correct weekdays for daily based workflows
    When calculating the dates for daily workflows - only week working days
    are taken into account. So neither start date nor end date can fall on
    a weekend. But can fall on holiday.
    Params:
    expected - last generated cycle start date
    """
    with freeze_time(freeze_date):
      with factories.single_commit():
        workflow = wf_factories.WorkflowFactory(repeat_every=repeat_every,
                                                unit=Workflow.DAY_UNIT)
        group = wf_factories.TaskGroupFactory(workflow=workflow)
        wf_factories.TaskGroupTaskFactory(
            task_group=group,
            start_date=setup_date,
            end_date=setup_date + dtm.timedelta(days=repeat_every))
      self.generator.activate_workflow(workflow)

    active_wf = db.session.query(Workflow).filter(
        Workflow.status == 'Active').one()
    self.assertEqual(len(active_wf.cycles), expected_num)
    last_cycle_task = active_wf.cycles[-1].cycle_task_group_object_tasks[0]
    self.assertEqual(expected_date, last_cycle_task.start_date)


class TestBasicWorkflowActions(TestCase):
  """
  Tests for basic workflow actions
  """
  def setUp(self):
    super(TestBasicWorkflowActions, self).setUp()
    self.api = Api()
    self.generator = WorkflowsGenerator()
    self.object_generator = ObjectGenerator()

    self.random_objects = self.object_generator.generate_random_objects()
    self.create_test_cases()

  def tearDown(self):
    pass

  def test_create_workflows(self):
    _, wflow = self.generator.generate_workflow(self.one_time_workflow_1)
    self.assertIsInstance(wflow, Workflow)

    task_groups = db.session.query(TaskGroup)\
        .filter(TaskGroup.workflow_id == wflow.id).all()

    self.assertEqual(len(task_groups),
                     len(self.one_time_workflow_1["task_groups"]))

  def test_workflows(self):
    for workflow in self.all_workflows:
      _, wflow = self.generator.generate_workflow(workflow)
      self.assertIsInstance(wflow, Workflow)

      task_groups = db.session.query(TaskGroup)\
          .filter(TaskGroup.workflow_id == wflow.id).all()

      self.assertEqual(len(task_groups),
                       len(workflow["task_groups"]))

  def test_activate_wf(self):
    for workflow in self.all_workflows:
      _, wflow = self.generator.generate_workflow(workflow)
      response, wflow = self.generator.activate_workflow(wflow)

      self.assert200(response)

  def test_one_time_workflow_edits(self):
    _, wflow = self.generator.generate_workflow(self.one_time_workflow_1)

    wf_dict = {"title": "modified one time wf"}
    self.generator.modify_workflow(wflow, data=wf_dict)

    modified_wf = db.session.query(Workflow).filter(
        Workflow.id == wflow.id).one()
    self.assertEqual(wf_dict["title"], modified_wf.title)

  def test_one_time_wf_activate(self):
    _, wflow = self.generator.generate_workflow(self.one_time_workflow_1)
    self.generator.generate_cycle(wflow)
    self.generator.activate_workflow(wflow)

    tasks = [len(tg.get("task_group_tasks", []))
             for tg in self.one_time_workflow_1["task_groups"]]

    cycle_tasks = db.session.query(CycleTaskGroupObjectTask).join(
        Cycle).join(Workflow).filter(Workflow.id == wflow.id).all()
    active_wf = db.session.query(Workflow).filter(
        Workflow.id == wflow.id).one()

    self.assertEqual(sum(tasks), len(cycle_tasks))
    self.assertEqual(active_wf.status, "Active")

  def test_one_time_wf_state_transition_dates(self):
    _, wflow = self.generator.generate_workflow(self.one_time_workflow_1)
    self.generator.generate_cycle(wflow)
    self.generator.activate_workflow(wflow)

    cycle_tasks = db.session.query(CycleTaskGroupObjectTask).join(
        Cycle).join(Workflow).filter(Workflow.id == wflow.id).all()
    with freeze_time("2015-6-9 13:00:00"):
      today = dtm.datetime.now()
      transitions = [
          ("InProgress", None, None),
          ("Finished", today, None),
          ("Declined", None, None),
          ("Finished", today, None),
          ("Verified", today, today),
          ("Finished", today, None),
      ]
      # Iterate over possible transitions and check if dates got set correctly
      for (status, expected_finished, expected_verified) in transitions:
        cycle_task = cycle_tasks[0]
        _, task = self.generator.modify_object(cycle_task, {"status": status})
        self.assertEqual(task.finished_date, expected_finished)
        self.assertEqual(task.verified_date, expected_verified)

  def test_delete_calls(self):
    _, workflow = self.generator.generate_workflow()
    self.generator.generate_task_group(workflow)
    _, task_group = self.generator.generate_task_group(workflow)
    task_groups = db.session.query(TaskGroup).filter(
        TaskGroup.workflow_id == workflow.id).all()
    self.assertEqual(len(task_groups), 2)

    response = self.generator.api.delete(task_group)
    self.assert200(response)

    task_groups = db.session.query(TaskGroup).filter(
        TaskGroup.workflow_id == workflow.id).all()
    self.assertEqual(len(task_groups), 1)

  def create_test_cases(self):

    self.quarterly_wf_1 = {
        "title": "quarterly wf 1",
        "description": "",
        "unit": "month",
        "repeat_every": 3,
        "task_groups": [{
            "title": "tg_1",
            "task_group_tasks": [{
                "description": factories.random_str(100),
            }, {
                "description": factories.random_str(100),
            }, {
                "description": factories.random_str(100),
            },
            ],
        },
        ]
    }

    self.weekly_wf_1 = {
        "title": "weekly thingy",
        "description": "start this many a time",
        "unit": "week",
        "repeat_every": 1,
        "task_groups": [{
            "title": "tg_2",
            "task_group_tasks": [{
                "description": factories.random_str(100),
            }, {
                "title": "monday task",
            }, {
                "title": "weekend task",
            },
            ],
            "task_group_objects": self.random_objects
        },
        ]
    }

    self.one_time_workflow_1 = {
        "title": "one time wf test",
        "description": "some test workflow",
        "task_groups": [{
            "title": "tg_1",
            "task_group_tasks": [{}, {}, {}]
        }, {
            "title": "tg_2",
            "task_group_tasks": [{
                "description": factories.random_str(100)
            }, {}
            ],
            "task_group_objects": self.random_objects[:2]
        }, {
            "title": "tg_3",
            "task_group_tasks": [{
                "title": "simple task 1",
                "description": factories.random_str(100)
            }, {
                "title": factories.random_str(),
                "description": factories.random_str(100)
            }, {
                "title": factories.random_str(),
                "description": factories.random_str(100)
            }
            ],
            "task_group_objects": self.random_objects
        }
        ]
    }
    self.one_time_workflow_2 = {
        "title": "test_wf_title",
        "description": "some test workflow",
        "task_groups": [
            {
                "title": "tg_1",
                "task_group_tasks": [{}, {}, {}]
            },
            {
                "title": "tg_2",
                "task_group_tasks": [{
                    "description": factories.random_str(100)
                }, {}],
                "task_group_objects": self.random_objects[:2]
            },
            {
                "title": "tg_3",
                "task_group_tasks": [{
                    "title": "simple task 1",
                    "description": factories.random_str(100)
                }, {
                    "title": factories.random_str(),
                    "description": factories.random_str(100)
                }, {
                    "title": factories.random_str(),
                    "description": factories.random_str(100)
                }],
                "task_group_objects": []
            }
        ]
    }

    self.monthly_workflow_1 = {
        "title": "monthly test wf",
        "description": "start this many a time",
        "unit": "month",
        "repeat_every": 1,
        "task_groups": [
            {
                "title": "tg_2",
                "task_group_tasks": [{
                    "description": factories.random_str(100),
                }, {
                    "title": "monday task",
                }, {
                    "title": "weekend task",
                }],
                "task_group_objects": self.random_objects
            },
        ]
    }
    self.all_workflows = [
        self.one_time_workflow_1,
        self.one_time_workflow_2,
        self.weekly_wf_1,
        self.monthly_workflow_1,
        self.quarterly_wf_1,
    ]
