# Inventaire du matériel de laboratoire

Application web (Streamlit) pour gérer l'inventaire du matériel de physique, chimie,
SVT et informatique, ainsi que les produits chimiques du laboratoire — consultable et
modifiable depuis n'importe quel appareil (ordinateur, smartphone, tablette).

## Fonctionnalités

- **Consultation** : parcourir, filtrer (catégorie, salle) et rechercher les articles,
  les modifier ou les supprimer.
- **Ajouter un article** : ajout libre à tout moment, avec photo (webcam ou fichier),
  nom, quantité, salle, armoire. Champs sécurité spécifiques pour les produits chimiques
  (n° CAS, pictogrammes SGH, date de péremption).
- **Session d'inventaire** : mode "pointage" pour parcourir le matériel existant salle
  par salle / catégorie par catégorie et mettre à jour les quantités constatées.
- **Données & Export** : accès direct au tableau de bord Supabase, export CSV, historique
  des sessions d'inventaire.

## Catégories disponibles

Optique, Mécanique, Électricité, Thermodynamique, Acoustique, Électrostatique,
Magnétisme, Appareils de mesure, Matériel de chimie, Verrerie, Produits chimiques,
Sécurité, Matériel informatique.

## Architecture

- **Interface** : Streamlit
- **Données** : Supabase (Postgres) — aucune base de données à héberger soi-même, modifiable
  aussi directement dans le tableau de bord Supabase si besoin
- **Photos** : Supabase Storage
- **Hébergement** : Streamlit Community Cloud (gratuit), déployé automatiquement depuis
  ce dépôt GitHub

## Démarrage

👉 **La procédure complète de configuration et de mise en ligne est dans [SETUP.md](SETUP.md).**
Elle couvre la création du projet Supabase, la création des tables et du bucket de photos,
puis le déploiement sur Streamlit Cloud.

### Test en local (optionnel)

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# puis complète .streamlit/secrets.toml avec tes propres identifiants (voir SETUP.md)
streamlit run app.py
```
