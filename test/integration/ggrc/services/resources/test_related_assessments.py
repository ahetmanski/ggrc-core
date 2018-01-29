# Copyright (C) 2018 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Tests for /api/related_assessments endpoint.

These tests only check the data returned by related assessments endpoint.
There are other tests for verifying completeness of the results and that focus
more on verifying the related SQL query.
"""

import ddt

from integration.ggrc.models import factories
from integration.ggrc.services import TestCase


@ddt.ddt
class TestRelatedAssessments(TestCase):
  """Tests for special people api endpoints."""

  URL_BASE = "/api/related_assessments"

  def setUp(self):
    super(TestRelatedAssessments, self).setUp()
    self.client.get("/login")
    with factories.single_commit():
      self.assessment1 = factories.AssessmentFactory(title="A_1")
      self.assessment2 = factories.AssessmentFactory(title="A_2")
      self.control = factories.ControlFactory()
      snap1 = self._create_snapshots(self.assessment1.audit, [self.control])
      snap2 = self._create_snapshots(self.assessment2.audit, [self.control])
      factories.RelationshipFactory(
          source=snap1[0],
          destination=self.assessment1
      )
      factories.RelationshipFactory(
          destination=snap2[0],
          source=self.assessment2,
      )
      factories.RelationshipFactory(
          source=self.assessment1.audit,
          destination=self.assessment1,
      )
      factories.RelationshipFactory(
          destination=self.assessment2.audit,
          source=self.assessment2,
      )

  def _get_related_assessments(self, obj, **kwargs):
    """Helper for retrieving assessment related objects."""
    kwargs["object_type"] = obj.type
    kwargs["object_id"] = obj.id
    return self.client.get(self.URL_BASE, query_string=kwargs)

  def test_basic_response(self):
    """Test basic response for a valid query."""
    assessment2_title = self.assessment2.title
    response = self._get_related_assessments(self.assessment1).json
    self.assertEqual(len(response), 1)
    self.assertEqual(response[0]["title"], assessment2_title)

  @ddt.data(
      {},
      {"a": 55},
      {"object_type": "invalid", "object_id": 5},
      {"object_type": "Control", "object_id": "invalid"},
      {"object_type": "Control", "object_id": 5, "limit": "a,b"},
      {"object_type": "Control", "object_id": 5, "limit": "1"},
      {"object_type": "Control", "object_id": 5, "limit": "1,2,5"},
      {"object_type": "Control", "object_id": 5, "limit": "5,1"},
      {"object_type": "Control", "object_id": 5, "limit": "-5,-1"},
  )
  def test_invalid_parameters(self, query_string):
    """Test invalid query parameters {0}."""
    self.assert400(self.client.get(self.URL_BASE, query_string=query_string))

  @ddt.data(
      ({}, 2),
      ({"limit": "0,1"}, 1),
      ({"limit": "1,2"}, 1),
      ({"limit": "1,3"}, 1),
      ({"limit": "0,2"}, 2),
      ({"limit": "0,7"}, 2),
  )
  @ddt.unpack
  def test_limit_clause(self, limit, expected_count):
    """Test limit clause for {0}."""
    response = self._get_related_assessments(self.control, **limit).json
    self.assertEqual(len(response), expected_count)

  @ddt.data(
      ({"order_by": "title"}, ["A_1", "A_2"]),
      ({"order_by": "title,asc"}, ["A_1", "A_2"]),
      ({"order_by": "title,desc"}, ["A_2", "A_1"]),
  )
  @ddt.unpack
  def test_order_by_clause(self, order_by, titles_order):
    """Test order by for {0}."""
    response = self._get_related_assessments(self.control, **order_by).json
    titles = [assessment["title"] for assessment in response]
    self.assertEqual(titles, titles_order)
