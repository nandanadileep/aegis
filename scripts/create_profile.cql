// Person
MERGE (p:Person {id: 'nandana_dileep'})
SET p.name = 'Nandana Dileep',
    p.ageRange = 'Early 20s',
    p.gender = 'Woman',
    p.country = 'India (Bangalore)',
    p.nativeLanguage = 'Malayalam (likely)',
    p.otherLanguages = ['English (strong)', 'Hindi (likely)'];

// Cultural & Social Context
MATCH (p:Person {id: 'nandana_dileep'})
MERGE (c:CulturalSocial {id: 'cultural_nandana'})
SET c.culturalBackground = 'Indian; academically competitive environment',
    c.religion = 'Not specified',
    c.familyStructure = 'Close parental involvement',
    c.livingSituation = 'Lives alone in Bangalore',
    c.socioeconomicContext = 'Educated, professional, urban middle/upper-middle class'
MERGE (p)-[:HAS_CULTURAL_CONTEXT]->(c);

// Education & Knowledge Level
MATCH (p:Person {id: 'nandana_dileep'})
MERGE (e:Education {id: 'education_nandana'})
SET e.highestEducationLevel = 'BTech, IIT Madras (2024)',
    e.fieldsOfStudy = ['Engineering'],
    e.expertiseAreas = [
        'Machine Learning',
        'Deep Learning (CNNs, ViT)',
        'LLM systems',
        'RAG systems',
        'Model fine-tuning (LoRA/QLoRA, RL)',
        'Data Science (Pandas, NumPy, Matplotlib)'
    ],
    e.beginnerAreas = [
        'Startup operations at scale',
        'Infrastructure at very large production scale',
        'Legal/financial structuring of companies'
    ]
MERGE (p)-[:HAS_EDUCATION]->(e);

// Occupation & Economic Context
MATCH (p:Person {id: 'nandana_dileep'})
MERGE (o:Occupation {id: 'occupation_nandana'})
SET o.employmentStatus = 'Full-time employed',
    o.profession = 'Data Scientist (AI/ML), Automotive',
    o.incomeBracket = 'Early-career engineer',
    o.workSchedule = 'Standard corporate schedule'
MERGE (p)-[:HAS_OCCUPATION]->(o);

// Personality & Cognitive Style
MATCH (p:Person {id: 'nandana_dileep'})
MERGE (ps:Personality {id: 'personality_nandana'})
SET ps.introversion = 'High-functioning introvert with ambition',
    ps.riskTolerance = 'Moderately high',
    ps.decisionMakingStyle = 'Analytical first, emotional second',
    ps.opennessToNewIdeas = 'Very high',
    ps.conflictStyle = 'Independent; seeks validation when challenged',
    ps.attentionToDetail = 'Strong detail focus; research-driven'
MERGE (p)-[:HAS_PERSONALITY]->(ps);

// Communication Preferences
MATCH (p:Person {id: 'nandana_dileep'})
MERGE (comm:Communication {id: 'communication_nandana'})
SET comm.tonePreference = 'Direct, sharp, structured',
    comm.responseLength = 'Concise unless depth requested',
    comm.structurePreference = 'Structured, bullet-based, sometimes code-only',
    comm.toleranceForDebate = 'High (prefers intellectual friction)',
    comm.humorPreference = 'Dad jokes; dark humour'
MERGE (p)-[:HAS_COMMUNICATION_PREFS]->(comm);

// Goals & Motivations
MATCH (p:Person {id: 'nandana_dileep'})
MERGE (g:Goals {id: 'goals_nandana'})
SET g.shortTermGoals = [
        'Strengthen AI/ML systems expertise',
        'Build and ship products (ShipCV, audio app, LLM systems)',
        'Position for startup or international move'
    ],
    g.longTermAspirations = [
        'Become a CEO',
        'Build an AI company',
        'Move abroad (Dubai considered)'
    ],
    g.coreValues = ['Independence', 'Competence', 'Discipline', 'Intellectual growth'],
    g.definitionOfSuccess = 'Authority + autonomy + impact; financial independence; leadership',
    g.primaryFears = ['Stagnation', 'Being underestimated', 'Wasting potential']
MERGE (p)-[:HAS_GOALS]->(g);

// Health & Physical Context
MATCH (p:Person {id: 'nandana_dileep'})
MERGE (h:Health {id: 'health_nandana'})
SET h.healthCondition = 'Healthy',
    h.disabilities = 'None mentioned',
    h.dietType = 'Not specified',
    h.sleepSchedule = 'Not specified',
    h.activityLevel = '5 days/week workouts (weights + Pilates focus)'
MERGE (p)-[:HAS_HEALTH]->(h);

// Technology Context
MATCH (p:Person {id: 'nandana_dileep'})
MERGE (t:Technology {id: 'technology_nandana'})
SET t.devicesUsed = ['MacBook', 'iPhone', 'AirPods Max', 'Alexa Echo'],
    t.operatingSystems = ['macOS', 'iOS'],
    t.internetLiteracy = 'Advanced',
    t.aiFamiliarity = 'Professional / advanced'
MERGE (p)-[:HAS_TECH_CONTEXT]->(t);

// Emotional Context
MATCH (p:Person {id: 'nandana_dileep'})
MERGE (em:Emotional {id: 'emotional_nandana'})
SET em.stressLevel = 'Ambitious but occasionally pressured',
    em.currentMood = 'Growth-oriented',
    em.majorLifeEvents = ['Early career phase', 'Product-building phase'],
    em.stabilityPhase = 'Transition-building (career evolution)'
MERGE (p)-[:HAS_EMOTIONAL_STATE]->(em);

// Legal & Geographic Context
MATCH (p:Person {id: 'nandana_dileep'})
MERGE (l:Legal {id: 'legal_nandana'})
SET l.legalSystem = 'Indian',
    l.visaStatus = 'Considering international relocation',
    l.taxRegime = 'Indian tax system'
MERGE (p)-[:HAS_LEGAL_CONTEXT]->(l);

// Privacy Boundaries
MATCH (p:Person {id: 'nandana_dileep'})
MERGE (pr:Privacy {id: 'privacy_nandana'})
SET pr.topicsToAvoid = ['Not explicitly defined'],
    pr.sensitivityThreshold = 'High privacy on personal independence issues',
    pr.dataRetentionPreference = 'Not specified'
MERGE (p)-[:HAS_PRIVACY_PREFS]->(pr);
