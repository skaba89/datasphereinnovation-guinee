const expertiseGroups=[
  {name:'Data, Analytics & IA',items:[
    ['database','Data Engineering','ETL/ELT, pipelines batch et streaming, ingestion, orchestration, CDC, qualité, observabilité et DataOps.'],
    ['network','Architecture Data','Lakehouse, Data Warehouse, Data Mesh, modélisation, migration, architecture cloud et hybride.'],
    ['chart','Business Intelligence & Analytics','Power BI, tableaux de bord, KPI, reporting, self-service BI, modélisation décisionnelle.'],
    ['shield','Gouvernance & qualité Data','Catalogue, lineage, MDM, référentiels, sécurité, confidentialité et contrats de données.'],
    ['brain','Intelligence artificielle & Data Science','Machine learning, NLP, IA générative, RAG, agents, MLOps et évaluation.']
  ]},
  {name:'Ingénierie numérique & SaaS',items:[
    ['layers','Architecture SI & solutions','Architecture d’entreprise, urbanisation, microservices, API, intégration et interopérabilité.'],
    ['code','Développement logiciel','Web, mobile, PWA, API, applications métiers et automatisation.'],
    ['cloud','Édition & architecture SaaS','Multi-tenant, abonnements, isolation, offline-first, intégrations et support.'],
    ['gear','Cloud, DevOps & SRE','Azure, AWS, GCP, conteneurs, CI/CD, infrastructure as code, supervision et fiabilité.'],
    ['shield','Cybersécurité & DevSecOps','Sécurité applicative, IAM, gestion des secrets, revue des risques et continuité.'],
    ['audit','Qualité logicielle & recette','Stratégie de tests, automatisation, recette métier, performance et non-régression.']
  ]},
  {name:'Finance, performance & audit',items:[
    ['finance','Contrôle de gestion & FP&A','Budgets, prévisions, écarts, coûts, marges, rentabilité et tableaux de bord de gestion.'],
    ['chart','Finance, comptabilité & reporting','Consolidation des données financières, rapprochements, reporting et digitalisation des processus.'],
    ['audit','Audit & contrôle interne','Audit SI, Data et processus, cartographie des risques, contrôle interne et plans de remédiation ; hors certification réglementée.']
  ]},
  {name:'Conseil, delivery & développement commercial',items:[
    ['target','Transformation digitale & stratégie','Diagnostic, feuille de route, cadrage, choix de solutions et accompagnement du changement.'],
    ['briefcase','Avant-vente & ingénierie commerciale','Qualification, ateliers, démonstrations sur rendez-vous, POC, chiffrage et propositions techniques.'],
    ['document','Appels d’offres & marchés','Veille, analyse du dossier de consultation, réponse technique, méthodologie, planning et budget.'],
    ['users','Pilotage de projet & produit','PMO, chef de projet, Product Owner, Scrum Master, coordination, conduite du changement et formation.']
  ]},
  {name:'Cybersécurité, risques & résilience',items:[
    ['shield','Audit de cybersécurité & GRC','Analyse des risques, gouvernance SSI, politiques de sécurité, écarts aux référentiels ISO 27001 et NIST, accompagnement RSSI.'],
    ['lock','Identités, accès & Zero Trust','IAM, MFA, SSO, RBAC, moindre privilège, gouvernance des accès et comptes privilégiés (PAM).'],
    ['cloud','Sécurité Cloud & infrastructures','Durcissement, segmentation réseau, chiffrement, sécurité des conteneurs et configurations cloud et hybrides.'],
    ['code','Sécurité applicative & tests autorisés','Revue de code, OWASP, SAST, DAST, SCA, gestion des vulnérabilités et tests d’intrusion sur périmètre autorisé.'],
    ['radar','Détection, SOC & réponse aux incidents','Collecte des journaux, SIEM, EDR, scénarios de détection, qualification et procédures de réponse aux incidents.'],
    ['backup','Cyberrésilience & continuité d’activité','Sauvegardes, restauration, plans PCA/PRA, exercices de crise et maîtrise des risques de rançongiciel.'],
    ['users','Sensibilisation & protection des données','Formation, simulations de phishing autorisées, classification, confidentialité et bonnes pratiques de protection des données.']
  ]}
];
const expertiseContainer=document.querySelector('#expertise-groups');
function expertiseId(name){return name.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')}
const expertiseDetails=[
  ['Flux fiables et industrialisés','Audit des flux, ingestion, orchestration, tests et supervision','Cartographie des flux, pipelines documentés, contrôles et runbook'],
  ['Une plateforme évolutive','Choix d’architecture, modélisation et trajectoire de migration','Architecture cible, schémas et plan de migration'],
  ['Des décisions fondées sur les données','Ateliers KPI, modèles décisionnels et tableaux de bord','Dictionnaire KPI, rapports et guide utilisateur'],
  ['Confiance dans les données','Diagnostic qualité, référentiels et responsabilités','Catalogue, règles qualité et plan de gouvernance'],
  ['Des usages IA maîtrisés','Cadrage des usages, prototypage, évaluation et garde-fous','POC évalué, documentation et plan MLOps'],
  ['Un SI cohérent et interopérable','Cartographie, urbanisation, API et intégration','Schéma directeur, architecture cible et contrats API'],
  ['Des applications adaptées aux usages','Conception UX, développement, intégration et tests','Application, code documenté et recette'],
  ['Des plateformes SaaS pérennes','Modularité, isolation, facturation et disponibilité','Architecture multi-tenant, stratégie de tests et exploitation'],
  ['Des déploiements reproductibles','Infrastructure, CI/CD, supervision et sauvegardes','Pipelines, infrastructure as code et procédures'],
  ['Une sécurité intégrée dès la conception','Analyse de risques, IAM et revue technique','Plan de remédiation, contrôles et recommandations'],
  ['Une qualité démontrable','Stratégie de tests, automatisation et recette métier','Plan de tests, rapport de recette et anomalies'],
  ['Un pilotage financier opérationnel','Budget, prévision, analyse des écarts et rentabilité','Modèle budgétaire, tableaux de bord et indicateurs'],
  ['Un reporting financier cohérent','Rapprochements, consolidation et automatisation','Cartographie des données, rapports et contrôles'],
  ['Des processus maîtrisés','Diagnostic SI, risques, contrôles et recommandations','Rapport d’audit de conseil et plan de remédiation'],
  ['Une transformation pragmatique','Diagnostic, priorisation et conduite du changement','Feuille de route et plan d’accompagnement'],
  ['Une proposition adaptée au besoin','Qualification, ateliers, estimation et dossier technique','Note de cadrage, chiffrage et proposition'],
  ['Une réponse structurée aux consultations','Analyse des exigences, conformité documentaire et planning','Matrice de conformité, mémoire technique et budget'],
  ['Une livraison pilotée par la valeur','Gouvernance, backlog, planification et coordination','Roadmap, reporting projet et critères de recette'],
  ['Un risque cyber identifié et piloté','Diagnostic SSI, cartographie des risques et analyse des écarts','Registre des risques, feuille de route SSI et plan de remédiation'],
  ['Des accès maîtrisés à chaque ressource','Inventaire des identités, politiques d’accès, MFA et revue des privilèges','Matrice des accès, architecture IAM et recommandations'],
  ['Une infrastructure durcie et segmentée','Revue de configuration, réseaux, secrets et conteneurs','Architecture sécurisée, liste des écarts et plan de durcissement'],
  ['Des applications plus résistantes','Revue applicative et tests convenus par écrit, en environnement autorisé','Rapport de vulnérabilités, priorisation et vérification des corrections'],
  ['Une détection et une réponse structurées','Analyse des journaux, scénarios de détection et préparation aux incidents','Catalogue de cas d’usage, procédures et tableau de bord'],
  ['Une reprise préparée et vérifiable','Analyse d’impact, RPO/RTO, sauvegarde et exercices de restauration','PCA/PRA, procédures de reprise et rapport d’exercice'],
  ['Des équipes sensibilisées et des données mieux protégées','Ateliers, classification, pratiques de sécurité et exercices autorisés','Supports de formation, recommandations et plan de sensibilisation']
];
const allExpertises=expertiseGroups.flatMap(g=>g.items.map(item=>({item,group:g.name})));
if(expertiseContainer){
  for(const group of expertiseGroups){
    const section=document.createElement('section');section.className='expertise-group';
    const title=document.createElement('h3');title.textContent=group.name;section.append(title);
    const grid=document.createElement('div');grid.className='expertise-grid';
    for(const [key,name,description] of group.items){
      const card=document.createElement('article');
      const mark=document.createElement('div');mark.className='expertise-icon';mark.append(icon(key));
      const heading=document.createElement('h4');heading.textContent=name;
      const p=document.createElement('p');p.textContent=description;
      const link=document.createElement('a');link.href='expertise.html?id='+encodeURIComponent(expertiseId(name));link.className='service-link';arrowLabel(link,'Découvrir cette expertise');
      card.append(mark,heading,p,link);grid.append(card);
    }
    section.append(grid);expertiseContainer.append(section);
  }
}
const detail=document.querySelector('#expertise-detail');
if(detail){
  const id=new URLSearchParams(location.search).get('id');
  const index=allExpertises.findIndex(({item})=>expertiseId(item[1])===id);
  if(index<0){detail.textContent='Expertise introuvable. Revenez à la page Expertises.'}
  else{
    const {item:[key,name,description],group}=allExpertises[index];
    const [benefit,scope,deliverables]=expertiseDetails[index];
    document.title=name+' | DSIG';
    for(const [field,value] of Object.entries({group,name,description,benefit,scope,deliverables}))document.getElementById(field).textContent=value;
    document.querySelector('#expertise-mark').append(icon(key));
    document.querySelector('#expertise-contact').href='index.html?expertise='+encodeURIComponent(id)+'#contact';
  }
}
