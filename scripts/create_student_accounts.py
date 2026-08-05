from etudiants.models import Etudiant
from users.models import CustomUser

print("Starting student accounts creation for existing students...")

etudiants_without_user = Etudiant.objects.filter(user__isnull=True)
count = 0

for etudiant in etudiants_without_user:
    # Extraire nom et prénom
    parts = etudiant.nom.split(' ', 1)
    nom = parts[0]
    prenom = parts[1] if len(parts) > 1 else ""

    # Création de l'utilisateur
    try:
        user = CustomUser.objects.create(
            noms=nom,
            prenoms=prenom,
            email=etudiant.email,
            role="etudiant"
        )
        
        # Récupération du mot de passe brut
        raw_password = getattr(user, '_raw_password', None)
        
        # Mise à jour de l'étudiant
        etudiant.user = user
        etudiant.initial_password = raw_password
        etudiant.save(update_fields=['user', 'initial_password'])
        
        count += 1
        print(f"Account created for: {etudiant.nom} (User: {user.username})")
    except Exception as e:
        print(f"Error creating account for {etudiant.nom}: {e}")

print(f"Finished! {count} accounts created.")
