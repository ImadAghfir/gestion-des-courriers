"""
Commande de vérification des échéances (cahier des charges §5.9).

    python manage.py verifier_echeances

Crée les notifications « Rappel J-2 » et « Courrier en retard ».
Peut être planifiée (Planificateur de tâches Windows / cron), mais la
vérification est aussi déclenchée automatiquement, au plus une fois par
heure, quand un utilisateur consulte ses notifications.
"""
from django.core.management.base import BaseCommand

from notifications.services import (
    CONSERVATION_NOTIFICATIONS_LUES,
    purger_notifications_lues,
    verifier_echeances,
)


class Command(BaseCommand):
    help = "Crée les alertes J-2 et retard, et purge les notifications lues anciennes."

    def add_arguments(self, analyseur):
        analyseur.add_argument(
            "--sans-purge",
            action="store_true",
            help="N'effectue pas la purge des notifications lues anciennes.",
        )

    def handle(self, *args, **options):
        rappels, retards = verifier_echeances()
        self.stdout.write(
            self.style.SUCCESS(
                f"Vérification terminée : {rappels} rappel(s) J-2, "
                f"{retards} alerte(s) de retard."
            )
        )

        if options["sans_purge"]:
            return

        supprimees = purger_notifications_lues()
        self.stdout.write(
            f"Purge : {supprimees} notification(s) lue(s) de plus de "
            f"{CONSERVATION_NOTIFICATIONS_LUES} jours supprimée(s)."
        )
