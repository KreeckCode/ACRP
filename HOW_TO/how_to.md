# Delete all migrations in your project
'''bash
    find . -path "*/migrations/0*.py" -not -name "__init__.py" -delete

# Flush the database4
'''bash
    python manage.py flush

# drop tables in your Postgres database to accommodate your migrations
'''bash
    DROP TABLE table_name;