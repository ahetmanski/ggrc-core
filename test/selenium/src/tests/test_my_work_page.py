# Copyright (C) 2017 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
"""My Work page smoke tests."""
# pylint: disable=no-self-use
# pylint: disable=invalid-name
# pylint: disable=too-few-public-methods
# pylint: disable=unused-argument

import pytest    # pylint: disable=import-error

from lib import base
from lib.constants import objects
from lib.page import dashboard, lhn
from lib.page.widget import generic_widget
from lib.utils import conftest_utils, selenium_utils


class TestMyWorkPage(base.Test):
  """Tests My Work page, part of smoke tests, section 2."""

  @pytest.mark.smoke_tests
  def test_horizontal_nav_bar_tabs(self, new_controls_rest, selenium):
    """Tests that several objects in widget can be deleted sequentially."""
    selenium.get(dashboard.Dashboard.URL)
    controls_widget = dashboard.Dashboard(selenium).select_controls()
    for _ in xrange(controls_widget.member_count):
      counter = controls_widget.get_items_count()
      (controls_widget.select_member_by_num(0).
       open_info_3bbs().select_delete().confirm_delete())
      controls_widget.wait_member_deleted(counter)
    assert generic_widget.Controls(
        selenium, objects.CONTROLS).members_listed == []

  @pytest.mark.smoke_tests
  def test_redirect(self, selenium):
    """Tests if user is redirected to My Work page after clicking on
    the my work button in user dropdown."""
    conftest_utils.navigate_to_page_with_lhn(selenium)
    dashboard.Header(selenium).select_my_work()
    assert selenium.current_url == dashboard.Dashboard.URL

  @pytest.mark.smoke_tests
  def test_lhn_stays_expanded(self, selenium):
    """Tests if, after opening LHN, it slides out and stays expanded."""
    conftest_utils.navigate_to_page_with_lhn(selenium)
    lhn_menu = dashboard.Header(selenium).open_lhn_menu()
    initial_position = lhn_menu.my_objects.element.location
    selenium_utils.wait_until_stops_moving(lhn_menu.my_objects.element)
    selenium_utils.hover_over_element(
        selenium, dashboard.Header(selenium).button_my_tasks.element)
    assert initial_position == lhn.Menu(selenium).my_objects.element.location

  @pytest.mark.smoke_tests
  def test_lhn_remembers_tab_state(self, selenium):
    """Tests if LHN remembers which tab is selected (my or all objects) after
    closing it."""
    conftest_utils.navigate_to_page_with_lhn(selenium)
    header = dashboard.Header(selenium)
    # check if my objects tab saves state
    lhn_menu = header.open_lhn_menu()
    lhn_menu.select_my_objects()
    header.close_lhn_menu()
    header.open_user_list()
    new_lhn = header.open_lhn_menu()
    assert selenium_utils.is_value_in_attr(new_lhn.my_objects.element) is True
    # check if all objects tab saves state
    lhn_menu = header.open_lhn_menu()
    lhn_menu.select_all_objects()
    header.close_lhn_menu()
    header.open_user_list()
    new_lhn = header.open_lhn_menu()
    assert selenium_utils.is_value_in_attr(new_lhn.all_objects.element) is True

  @pytest.mark.smoke_tests
  def test_lhn_pin(self, selenium):
    """Tests if pin is present and if it's default state is off."""
    conftest_utils.navigate_to_page_with_lhn(selenium)
    lhn_menu = dashboard.Header(selenium).open_lhn_menu()
    assert lhn_menu.pin.is_activated is False

  @pytest.mark.smoke_tests
  def test_user_menu_checkbox(self, selenium):
    """Tests user menu checkbox. With that also user menu itself is
    tested since model initializes all elements (and throws and
    exception if they're not present."""
    conftest_utils.navigate_to_page_with_lhn(selenium)
    user_list = dashboard.Header(selenium).open_user_list()
    user_list.checkbox_daily_digest.click()
    user_list.checkbox_daily_digest.element.get_attribute("disabled")
    # restore previous state
    user_list.checkbox_daily_digest.click()
