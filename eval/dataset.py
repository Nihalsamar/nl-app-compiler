"""Evaluation dataset: 10 realistic product prompts + 10 edge cases.

Edge cases deliberately probe vagueness, conflict, and underspecification so we
can measure how the system behaves under messiness, not just happy paths.
"""

REAL_PROMPTS = [
    "Build a CRM with login, contacts, dashboard, role-based access, and a premium plan with payments. Admins can see analytics.",
    "Build a task manager where users create tasks, set due dates, and mark them complete.",
    "Build an online store with products, orders, and an admin who sees sales analytics.",
    "Build a blog platform with posts, comments, and author accounts.",
    "Build a help desk where customers open tickets and agents respond.",
    "Build a project management tool with projects, tasks, and team members.",
    "Build an invoicing app where users create invoices for customers and track payments.",
    "Build a booking app for appointments with customers and staff calendars.",
    "Build a learning platform with courses, lessons, and enrolled students.",
    "Build an expense tracker where users log expenses by category with monthly reports.",
]

EDGE_PROMPTS = [
    "app",                                   # too vague -> should ask
    "make it good",                          # vague, no nouns
    "Build something with users.",           # underspecified
    "Build a free app with a paid premium-only free tier.",  # conflicting
    "Build a CRM but with no data and no users.",            # contradictory
    "Build an app to manage stuff and things.",              # non-specific nouns
    "Build a store with products but no way to buy them and also checkout.",  # conflict
    "Build a system.",                       # too vague
    "Build a social app with posts, but posts should not be stored.",  # contradictory
    "Build a dashboard.",                    # underspecified (no entities)
]
