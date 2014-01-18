# Copyright (C) 2013 Google Inc., authors, and contributors <see AUTHORS file>
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
# Created By: david@reciprocitylabs.com
# Maintained By: david@reciprocitylabs.com

from ggrc.extensions import get_extension_modules
from .roles import (
    Auditor, AuditorProgramReader, AuditorReader, ObjectEditor,
    ProgramAuditEditor, ProgramAuditOwner, ProgramAuditReader,
    ProgramBasicReader, ProgramCreator, ProgramEditor, ProgramOwner,
    ProgramReader, Reader, gGRC_ADMIN,
    )

DECLARED_ROLE = "CODE DECLARED ROLE"

def get_declared_role(rolename, resolved_roles={}):
  if rolename in resolved_roles:
    return resolved_roles[rolename]
  declarations = lookup_declarations()
  if rolename in declarations:
    role_definition = declarations[rolename]
    role_definition.permissions.update(lookup_contributions(rolename))
    resolved_roles[rolename] = role_definition
    return role_definition
  return None

def lookup_declarations(declarations={}):
  if len(declarations) == 0:
    extension_modules = get_extension_modules()
    for extension_module in extension_modules:
      ext_declarations = getattr(extension_module, "ROLE_DECLARATIONS", None)
      if ext_declarations:
        declarations.update(ext_declarations.roles())
    if len(declarations) == 0:
      declarations[None] = None
  if None in declarations:
    return {}
  else:
    return declarations

def lookup_contributions(rolename):
  extension_modules = get_extension_modules()
  contributions = {}
  for extension_module in extension_modules:
    ext_contributions = getattr(extension_module, "ROLE_CONTRIBUTIONS", None)
    if ext_contributions:
      contributions.update(ext_contributions.contributions_for(rolename))
  return contributions;

class RoleDeclarations(object):
  """
  A RoleDeclarations object provides the names of roles declared by this
  extension.

  A role declaration is an object with 3 properties: scope, description, and
  permissions. Scope and descriptions are strings, permissions MUST be a
  dict.
  """
  def roles(self):
    return {}

class RoleContributions(object):
  """
  A RoleContributions object provides role definition dictionaries by name.
  """
  def contributions_for(self, rolename):
    """
    look up a method in self for the role name, return value of method is the
    contribution.
    """
    method = getattr(self.__class__, rolename)
    if method:
      return method(self)
    return {}

class BasicRoleDeclarations(RoleDeclarations):
  def roles(self):
    return {
        'AuditorReader': AuditorReader,
        'Reader': Reader,
        'ProgramCreator': ProgramCreator,
        'ObjectEditor': ObjectEditor,
        'ProgramBasicReader': ProgramBasicReader,
        'ProgramOwner': ProgramOwner,
        'ProgramEditor': ProgramEditor,
        'ProgramReader': ProgramReader,
        'AuditorProgramReader': AuditorProgramReader,
        'ProgramAuditOwner': ProgramAuditOwner,
        'ProgramAuditEditor': ProgramAuditEditor,
        'ProgramAuditReader': ProgramAuditReader,
        'Auditor': Auditor,
        }
