# Copyright (C) 2017 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

from ggrc import db
from ggrc.fulltext.mixin import Indexed
from .mixins import BusinessObject, Timeboxed, CustomAttributable
from .object_owner import Ownable
from .object_person import Personable
from .relationship import Relatable
from .track_object_state import HasObjectState


class Vendor(HasObjectState, CustomAttributable, Personable,
             Relatable, Timeboxed, Ownable, BusinessObject, Indexed, db.Model):
  __tablename__ = 'vendors'

  _aliases = {
      "url": "Vendor URL",
      "reference_url": "Reference URL",
  }
