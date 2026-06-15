# backend-api_smartcampus

### Démarrage rapide (dev)
- **Backend**
  - Activer le venv: `source venv/bin/activate`
  - Lancer: `python manage.py migrate && python manage.py runserver`

- **Frontend** (`front-end_smartcampus/frontend`)
  - Créer `.env` à partir de `.env.example` et ajuster `VITE_API_BASE_URL`
  - Lancer: `npm install && npm run dev`

### Endpoints “robustes” à utiliser (API v2)
- **Pré-inscriptions**
  - `POST /api/v2/pre-inscriptions/` (formulaire public, inclure `filiere_souhaitee` et `niveau_souhaite`)
  - `POST /api/v2/pre-inscriptions/{id}/approve/` (admin: approuver + synchroniser Etudiant/Inscription)

- **Notes (par formation + niveau)**
  - `GET /api/v2/notes/export-template-niveau/?filiere=<idFormation>&niveau=<idNiveau>&session=Semestre 1`
  - `POST /api/v2/notes/import-notes-niveau/` (multipart: `filiere`, `niveau`, `session`, `file`)
  - `GET /api/v2/notes/par-filiere-niveau/?filiere_id=<idFormation>&session=Semestre 1`
  - `GET /api/v2/notes/par-module/?module_id=<idModule>&session=Semestre 1`

  ### Utiliser Supabase (Postgres) comme base de données

  - Définir la variable d'environnement `DATABASE_URL` avec la connection string fournie par Supabase, par exemple:
    `postgres://user:password@db.host:5432/database`
  - Installer les nouvelles dépendances et migrer:
  ```bash
  source venv/bin/activate
  pip install -r requirements.txt
  python manage.py migrate
  python manage.py runserver
  ```

  Le projet retombera sur SQLite si `DATABASE_URL` n'est pas défini (utile pour le dev local).
