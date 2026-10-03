from django.db import migrations, models


def transferer_affectations_provisoires(apps, schema_editor):
    Courrier = apps.get_model("courriers", "Courrier")
    for courrier in Courrier.objects.exclude(affectation_provisoire__isnull=True):
        courrier.affectations_provisoires.add(courrier.affectation_provisoire_id)


class Migration(migrations.Migration):

    dependencies = [
        ("courriers", "0003_alter_courrier_statut"),
    ]

    operations = [
        migrations.AddField(
            model_name="courrier",
            name="affectations_provisoires",
            field=models.ManyToManyField(
                blank=True,
                help_text="Départements probables proposés par le Bureau d'Ordre (non officiels).",
                related_name="courriers_proposes",
                to="services.departement",
            ),
        ),
        migrations.RunPython(transferer_affectations_provisoires, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="courrier",
            name="affectation_provisoire",
        ),
    ]
