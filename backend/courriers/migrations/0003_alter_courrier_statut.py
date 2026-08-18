# Migration neutralisée lors du passage à la version 3.3.
# L'ancien contenu (modification des choix de statut) est remplacé par la
# nouvelle chaîne de migrations initiales (0001 → 0003_initial).
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("courriers", "0003_initial"),
    ]

    operations = []
