"""Bilingual acknowledgement templates; no user-supplied text in email markup."""
from html import escape

# Stable form values, translated labels and next step.
TYPES = {
    "Demande de devis": ("Demande de devis", "Quote request", "Nous analyserons votre besoin pour préparer une proposition chiffrée adaptée.", "We will review your needs to prepare a tailored, priced proposal."),
    "Formation": ("Formation", "Training", "Nous étudierons les publics, les objectifs et le format de formation souhaités.", "We will review the audience, objectives and training format you need."),
    "Autre demande": ("Autre demande", "Other request", "Nous orienterons votre demande vers l’interlocuteur approprié.", "We will route your request to the right contact."),
    "Mission en régie": ("Mission en régie", "Staff augmentation", "Nous analyserons les compétences, la disponibilité et la durée de la mission.", "We will review the skills, availability and duration required."),
    "Projet au forfait": ("Projet au forfait", "Fixed-price project", "Nous étudierons le périmètre, les livrables et les contraintes pour préparer un échange de cadrage.", "We will review the scope, deliverables and constraints to prepare a scoping discussion."),
    "Demande de démonstration": ("Demande de démonstration", "Product demonstration", "Notre équipe préparera une présentation de la solution demandée.", "Our team will prepare a presentation of the requested solution."),
    "Plateforme Analytics / BI": ("Analytics / BI", "Analytics / BI", "Nous étudierons vos sources, indicateurs et besoins de pilotage.", "We will review your data sources, indicators and reporting needs."),
    "Transformation numérique": ("Transformation numérique", "Digital transformation", "Nous examinerons vos processus, objectifs et priorités de digitalisation.", "We will review your processes, objectives and digitalisation priorities."),
    "Data & IA": ("Data & IA", "Data & AI", "Nous examinerons les cas d’usage, les données et les objectifs de valeur.", "We will review your use cases, data and value objectives."),
    "Partenariat": ("Partenariat", "Partnership", "Nous évaluerons les complémentarités et les modalités de collaboration.", "We will assess opportunities for collaboration and complementary capabilities."),
    "Conseil & expertise": ("Conseil & expertise", "Consulting & expertise", "Nous identifierons les expertises adaptées à votre contexte.", "We will identify the expertise suited to your context."),
    "Contrôle de gestion & finance": ("Contrôle de gestion & finance", "Management accounting & finance", "Nous examinerons vos besoins de pilotage financier et de reporting.", "We will review your financial management and reporting needs."),
    "Audit & contrôle interne": ("Audit & contrôle interne", "Audit & internal control", "Nous étudierons le périmètre et les objectifs du contrôle.", "We will review the scope and objectives of the assessment."),
    "Avant-vente & appels d’offres": ("Avant-vente & appels d’offres", "Pre-sales & tenders", "Nous examinerons le calendrier, les exigences et le périmètre de la consultation.", "We will review the timeline, requirements and scope of the tender."),
    "Candidature spontanée": ("Candidature spontanée", "Unsolicited application", "Notre équipe RH examinera votre demande. Cet accusé ne constitue pas une offre d’emploi.", "Our HR team will review your application. This acknowledgement is not a job offer."),
    "Cybersécurité & résilience": ("Cybersécurité & résilience", "Cybersecurity & resilience", "Nous examinerons vos objectifs de sécurité et de résilience sans demander de secrets par e-mail.", "We will review your security and resilience objectives without requesting secrets by email."),
}

def render(reference, category, language):
    en = language == 'en'
    label_fr,label_en,step_fr,step_en = TYPES[category]
    label,step = (label_en,step_en) if en else (label_fr,step_fr)
    title = 'Your request has been received' if en else 'Votre demande a bien été reçue'
    greeting = 'Hello,' if en else 'Bonjour,'
    thanks = 'Thank you for contacting DataSphere Innovation Guinée (DSIG).' if en else 'Merci d’avoir contacté DataSphere Innovation Guinée (DSIG).'
    next_label = 'Next steps' if en else 'Prochaine étape'
    closing = 'Our team will get back to you after reviewing your request.' if en else 'Notre équipe reviendra vers vous après étude de votre demande.'
    ref_label = 'Reference' if en else 'Référence'
    test = 'TEST — no commercial commitment.' if en else 'RECETTE — aucun engagement commercial.'
    body = '\n\n'.join((greeting,thanks,f'{title} — {label}',f'{ref_label}: {reference}',f'{next_label}: {step}',closing,'DataSphere Innovation Guinée | DSIG Consulting',test))
    e = escape
    html = f"""<!doctype html><html lang="{'en' if en else 'fr'}"><body style="margin:0;background:#f5f2fa;font-family:Arial,sans-serif;color:#201038">
<table role="presentation" width="100%" cellspacing="0" cellpadding="20"><tr><td align="center">
<table role="presentation" width="100%" style="max-width:600px;background:#fff;border:1px solid #e3d9ee;border-radius:12px" cellspacing="0" cellpadding="24">
<tr><td style="background:#35104e;color:white;font-size:24px;font-weight:bold">DSIG | Consulting</td></tr>
<tr><td><h1 style="font-size:24px">{e(title)}</h1><p>{e(greeting)}</p><p>{e(thanks)}</p>
<p style="padding:14px;background:#f5f2fa"><strong>{e(label)}</strong><br>{e(ref_label)}: {e(reference)}</p>
<h2 style="font-size:18px;color:#604098">{e(next_label)}</h2><p>{e(step)}</p><p>{e(closing)}</p>
<p>DataSphere Innovation Guinée | DSIG Consulting</p></td></tr>
<tr><td style="background:#f5f2fa;color:#5b5068;font-size:12px">{e(test)}</td></tr></table>
</td></tr></table></body></html>"""
    return f'[REC TEST] DSIG — {label}',body,html


STATUS = {
    'NOUVELLE': ('Demande reçue','Request received','Nous avons reçu votre demande.','We have received your request.'),
    'QUALIFIEE': ('Demande qualifiée','Request qualified','Votre dossier a été examiné et orienté vers notre équipe.','Your request has been reviewed and assigned to our team.'),
    'EN_COURS': ('Demande en cours de traitement','Request in progress','Notre équipe étudie votre demande.','Our team is reviewing your request.'),
    'GAGNEE': ('Traitement terminé','Review completed','Le traitement de votre demande est terminé. Notre équipe vous informera des prochaines étapes.','The review is complete. Our team will advise you of the next steps.'),
    'PERDUE': ('Dossier clôturé','Request closed','Votre dossier est clôturé. Vous pouvez nous contacter pour toute question.','Your request is closed. Please contact us with any questions.'),
}

def render_status(reference,status,language):
    en=language=='en'
    fr,eng,fr_step,en_step=STATUS[status]
    label,step=(eng,en_step) if en else (fr,fr_step)
    ref_label='Reference' if en else 'Référence'
    notice='TEST — no commercial commitment.' if en else 'RECETTE — aucun engagement commercial.'
    subject=f'[REC TEST] DSIG — {label}'
    plain=f'{label}\n\n{ref_label}: {reference}\n\n{step}\n\nDataSphere Innovation Guinée | DSIG Consulting\n{notice}'
    markup=f'<html lang="{language}"><body style="font-family:Arial,sans-serif;color:#201038"><div style="background:#35104e;color:white;padding:20px;font-size:22px">DSIG | Consulting</div><h1>{escape(label)}</h1><p>{ref_label}: {escape(reference)}</p><p>{escape(step)}</p><p>DataSphere Innovation Guinée | DSIG Consulting</p><p>{escape(notice)}</p></body></html>'
    return subject,plain,markup
