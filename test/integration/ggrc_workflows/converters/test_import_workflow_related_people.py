# Copyright (C) 2017 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Tests for workflow related objects people imports."""
# pylint: disable=invalid-name

import collections
import string
import ddt

from ggrc_workflows.models.workflow import Workflow
from integration.ggrc import TestCase
from integration.ggrc.models import factories as ggrc_factories


@ddt.ddt
class TestWorkflowRelatedPeopleImport(TestCase):
  """Tests for workflow related objects people imports."""

  def setUp(self):
    self.users = []
    for _ in xrange(8):
      self.users.append(ggrc_factories.PersonFactory())
    self.users.sort(key=lambda u: u.email)
    self.wf_slug = ggrc_factories.random_str(chars=string.ascii_letters)
    self.wf_import_params = [
        ("object_type", "Workflow"),
        ("code", self.wf_slug),
        ("title", "SomeTitle"),
        ("Need Verification", 'True')
    ]

  def _get_people_emails_by_role(self, workflow, role_name):
    """Get people emails by user_role.

    Args:
        workflow: Workflow instance
        role_name: Workflow user role name

    Returns:
        People emails sorted by alphabet.
    """
    people_emails = []
    for wp in workflow.workflow_people:
      self.assertEqual(len(wp.person.user_roles), 1)
      if wp.person.user_roles[0].role.name == role_name:
        people_emails.append(wp.person.email)
    people_emails.sort()
    return people_emails

  def _check_workflow_people(self, owners_idx, members_idx,  # noqa pylint: disable=too-many-arguments,too-many-locals
                             expected_owners_idx, expected_members_idx,
                             is_success, success_resp_action):
    """Import people list to workflow and compare with expected results.

    Args:
        owners_idx: Indexes of the test people data who should get Owner role.
        members_idx: Indexes of the test people data who should get Member
            role.
        expected_owners_idx: Expected indexes for the people with Owner role.
        expected_members_idx: Expected indexes for the people with Member role.
        is_success: Shows is import was successful or not.
        success_resp_action: Action which was performed on imported item.
    """
    if members_idx:
      import_members = '\n'.join(
          (self.users[idx].email for idx in members_idx))
      self.wf_import_params.append(('member', import_members))
    if owners_idx:
      import_owners = '\n'.join((self.users[idx].email for idx in owners_idx))
      self.wf_import_params.append(('manager', import_owners))
    resp = self.import_data(collections.OrderedDict(self.wf_import_params))
    if is_success:
      self.assertEqual(resp[0][success_resp_action], 1)
      self._check_csv_response(resp, {})
      workflow = Workflow.query.filter(Workflow.slug == self.wf_slug).first()

      exst_owners = self._get_people_emails_by_role(workflow, 'WorkflowOwner')
      expected_owners = [self.users[idx].email for idx in expected_owners_idx]
      self.assertEqual(exst_owners, expected_owners)

      exst_members = self._get_people_emails_by_role(workflow,
                                                     'WorkflowMember')
      expected_members = [self.users[idx].email
                          for idx in expected_members_idx]
      self.assertEqual(exst_members, expected_members)
    else:
      self.assertEqual(resp[0]['ignored'], 1)

  @ddt.data(
      ([0, 1], [2, 3], [0, 1], [2, 3], True),
      ([0, 1], [1, 2], [0, 1], [2], True),
      ([0, 1], [0, 1], [0, 1], [], True),
      ([0, 1], [], [0, 1], [], True),
      ([], [0, 1], [], [], False),
      ([], [], [], [], False),
  )
  @ddt.unpack  # noqa pylint: disable=too-many-arguments
  def test_create_workflow_with_people(self, owners_idx, members_idx,
                                       expected_owners_idx,
                                       expected_members_idx, is_success):
    """Tests importing new workflow with lists of owners and members."""
    self._check_workflow_people(owners_idx, members_idx, expected_owners_idx,
                                expected_members_idx, is_success, 'created')

  @ddt.data(
      ([0, 1], [2, 3], [0, 1], [2, 3], True),
      ([0, 1], [1, 2], [0, 1], [2], True),
      ([0, 1], [0, 1], [0, 1], [4, 5], True),
      ([0, 1], [], [0, 1], [4, 5], True),
      ([4, 5], [], [4, 5], [], True),
      ([], [0, 1], [6, 7], [0, 1], True),
      ([], [], [6, 7], [4, 5], True),
  )
  @ddt.unpack  # noqa pylint: disable=too-many-arguments
  def test_update_workflow_with_people(self, owners_idx, members_idx,
                                       expected_owners_idx,
                                       expected_members_idx, is_success):
    """Tests importing existing workflow with lists of owners and members."""
    def_params = (
        self.wf_import_params +
        [
            ('member', '\n'.join((self.users[4].email, self.users[5].email))),
            ('manager', '\n'.join((self.users[6].email, self.users[7].email))),
        ]
    )
    self.import_data(collections.OrderedDict(def_params))
    self._check_workflow_people(owners_idx, members_idx, expected_owners_idx,
                                expected_members_idx, is_success, 'updated')

  @ddt.data(
      (4, 5, [2, 3, 4, 5]),
      (0, 1, [2, 3]),
      (0, 6, [2, 3, 6]),
      (7, 1, [2, 3, 7]),
      (2, 3, [2, 3]),
      (2, 4, [2, 3, 4]),
      (5, 3, [2, 3, 5])
  )
  @ddt.unpack
  def test_import_assignees(self, tg_assignee_id, tgt_assignee_id,
                            expected_members_idx):
    """Tests importing TaskGroup and TaskGroupTask with assignee."""
    self._check_workflow_people([0, 1], [2, 3], [0, 1], [2, 3], True,
                                'created')

    tg_slug = ggrc_factories.random_str(chars=string.ascii_letters)
    tg_import_params = [
        ("object_type", "Task Group"),
        ("code", tg_slug),
        ("summary", "SomeTitle"),
        ("assignee", self.users[tg_assignee_id].email),
        ("workflow", self.wf_slug),
    ]
    resp = self.import_data(collections.OrderedDict(tg_import_params))
    self.assertEqual(resp[0]['created'], 1)
    self._check_csv_response(resp, {})

    tgt_slug = ggrc_factories.random_str(chars=string.ascii_letters)
    tgt_import_params = [
        ("object_type", "Task"),
        ("code", tgt_slug),
        ("summary", "SomeTitle"),
        ("assignee", self.users[tgt_assignee_id].email),
        ("task group", tg_slug),
        ("task type", "Rich text"),
        ("start date", "7/1/2015"),
        ("end date", "7/15/2015")
    ]
    resp = self.import_data(collections.OrderedDict(tgt_import_params))
    self.assertEqual(resp[0]['created'], 1)
    self._check_csv_response(resp, {})

    workflow = Workflow.query.filter(Workflow.slug == self.wf_slug).first()
    exst_owners = self._get_people_emails_by_role(workflow, 'WorkflowOwner')
    expected_owners = [self.users[idx].email for idx in [0, 1]]
    self.assertEqual(exst_owners, expected_owners)
    exst_members = self._get_people_emails_by_role(workflow,
                                                   'WorkflowMember')
    expected_members = [self.users[idx].email for idx in expected_members_idx]
    self.assertEqual(exst_members, expected_members)
