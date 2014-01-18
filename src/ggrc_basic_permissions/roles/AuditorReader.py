scope = "System Implied"
description = """
  A user with Auditor role for a program audit will also have this role in the
  default object context so that the auditor will have access to the objects
  required to perform the audit. 
  """
permissions = {
    "read": [
        "Categorization",
        "Category",
        "Control",
        "ControlControl",
        "ControlSection",
        "DataAsset",
        "Directive",
        "Contract",
        "Policy",
        "Regulation",
        "Standard",
        "DirectiveControl",
        "Document",
        "Facility",
        "Help",
        "Market",
        "Objective",
        "ObjectiveControl",
        "ObjectControl",
        "ObjectDocument",
        "ObjectObjective",
        "ObjectPerson",
        "ObjectSection",
        "Option",
        "OrgGroup",
        "PopulationSample",
        "Product",
        "ProgramControl",
        "ProgramDirective",
        "Project",
        "Relationship",
        "RelationshipType",
        "Section",
        "SectionObjective",
        "SystemOrProcess",
        "System",
        "Process",
        "SystemControl",
        "SystemSystem",
        "ObjectOwner",
        "Person",
        "Program",
        "Role",
        "ObjectFolder",
        "ObjectFile"
    ],
    "create": [],
    "view_object_page": [],
    "update": [],
    "delete": []
}
