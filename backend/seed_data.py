import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from services.models import Service
from courriers.models import Courrier

User = get_user_model()

def seed():
    print("Seeding database...")
    # Clear existing data
    Courrier.objects.all().delete()
    User.objects.all().delete()
    Service.objects.all().delete()

    # Create Services
    dg = Service.objects.create(nom="Direction Générale", code="DG", statut=Service.Statut.ACTIF)
    rh = Service.objects.create(nom="Ressources Humaines", code="RH", statut=Service.Statut.ACTIF)
    it = Service.objects.create(nom="Service Informatique", code="IT", statut=Service.Statut.ACTIF)

    # Create Users
    admin_user = User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="adminpassword",
        role=User.Role.ADMIN,
        service=dg
    )
    
    resp_rh = User.objects.create_user(
        username="responsable_rh",
        email="resp_rh@example.com",
        password="rhpassword",
        role=User.Role.RESPONSABLE,
        service=rh
    )

    agent_it = User.objects.create_user(
        username="agent_it",
        email="agent_it@example.com",
        password="itpassword",
        role=User.Role.AGENT,
        service=it
    )

    # Update service responsables
    dg.responsable = admin_user
    dg.save()
    rh.responsable = resp_rh
    rh.save()
    it.responsable = agent_it
    it.save()

    # Create Courriers
    Courrier.objects.create(
        type_courrier=Courrier.TypeCourrier.ENTRANT,
        objet="Demande de partenariat DG",
        expediteur="Société Partenaire",
        categorie="Administratif",
        priorite=Courrier.Priorite.NORMAL,
        statut=Courrier.Statut.RECU,
        createur=admin_user,
        service=dg
    )

    Courrier.objects.create(
        type_courrier=Courrier.TypeCourrier.SORTANT,
        objet="Lettre de licenciement confidentielle",
        destinataire="Salarié X",
        categorie="RH",
        priorite=Courrier.Priorite.URGENT,
        statut=Courrier.Statut.BROUILLON,
        createur=resp_rh,
        service=rh
    )

    Courrier.objects.create(
        type_courrier=Courrier.TypeCourrier.SORTANT,
        objet="Commande de nouveaux serveurs IT",
        destinataire="Fournisseur Hardware",
        categorie="Achat",
        priorite=Courrier.Priorite.TRES_URGENT,
        statut=Courrier.Statut.EN_VALIDATION,
        createur=agent_it,
        service=it
    )

    print("Database seeded successfully!")
    print("Credentials:")
    print("  - Admin: admin / adminpassword")
    print("  - Responsable RH: responsable_rh / rhpassword")
    print("  - Agent IT: agent_it / itpassword")

if __name__ == "__main__":
    seed()
