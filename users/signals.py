# users/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from .models import CustomUser

@receiver(post_save, sender=CustomUser)
def send_credentials_email(sender, instance, created, **kwargs):
    # On récupère le mot de passe brut stocké temporairement
    raw_password = getattr(instance, "_raw_password", None)

    if raw_password:
        if created:
            subject = "Bienvenue - Vos identifiants de connexion"
            intro = f"Bonjour {instance.noms} {instance.prenoms},<br><br>Votre compte a été créé avec succès."
        else:
            subject = "Réinitialisation de votre mot de passe"
            intro = f"Bonjour {instance.noms} {instance.prenoms},<br><br>Votre mot de passe a été réinitialisé par l’administrateur."

        from_email = settings.DEFAULT_FROM_EMAIL
        to = [instance.email]

        # ✅ contenu texte brut (fallback)
        text_content = f"""
        {intro}

        Nom d’utilisateur : {instance.username}
        Mot de passe : {raw_password}

        Veuillez utiliser ces identifiants pour vous connecter.
        """

        # ✅ contenu HTML stylisé
        html_content = f"""
        <html>
          <body style="font-family: Arial, sans-serif; background-color:#f9f9f9; padding:20px;">
            <div style="max-width:600px; margin:auto; background:#fff; border-radius:8px; padding:20px; box-shadow:0 2px 5px rgba(0,0,0,0.1);">
              <h2 style="color:#007bff;">{subject}</h2>
              <p>{intro}</p>
              <table style="width:100%; border-collapse:collapse; margin:20px 0;">
                <tr>
                  <td style="padding:8px; border:1px solid #ddd;"><strong>Nom d’utilisateur</strong></td>
                  <td style="padding:8px; border:1px solid #ddd;">{instance.username}</td>
                </tr>
                <tr>
                  <td style="padding:8px; border:1px solid #ddd;"><strong>Mot de passe</strong></td>
                  <td style="padding:8px; border:1px solid #ddd;">{raw_password}</td>
                </tr>
              </table>
              <p style="color:#dc3545;"><strong>⚠️ Veuillez garder ces identifiants confidentiels.</strong></p>
              <p style="font-size:12px; color:#666;">Cet email est généré automatiquement, merci de ne pas y répondre.</p>
            </div>
          </body>
        </html>
        """

        msg = EmailMultiAlternatives(subject, text_content, from_email, to)
        msg.attach_alternative(html_content, "text/html")
        msg.send()