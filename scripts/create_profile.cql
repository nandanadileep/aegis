// Person
MERGE (p:Person {id: 'person_placeholder'})
SET p.name = 'Placeholder Name',
    p.ageRange = '25-34',
    p.gender = 'unspecified',
    p.country = 'Placeholder Country/Region',
    p.nativeLanguage = 'English',
    p.otherLanguages = ['Spanish', 'French'];

// Cultural & Social Context
MATCH (p:Person {id: 'person_placeholder'})
MERGE (c:CulturalSocial {id: 'cultural_placeholder'})
SET c.culturalBackground = 'Placeholder background',
    c.religion = 'Optional / undisclosed',
    c.familyStructure = 'Nuclear',
    c.livingSituation = 'Shared',
    c.socioeconomicContext = 'Middle income'
MERGE (p)-[:HAS_CULTURAL_CONTEXT]->(c);

// Education & Knowledge Level
MATCH (p:Person {id: 'person_placeholder'})
MERGE (e:Education {id: 'education_placeholder'})
SET e.highestEducationLevel = 'Bachelors',
    e.fieldsOfStudy = ['Computer Science'],
    e.expertiseAreas = ['Software Engineering'],
    e.beginnerAreas = ['Hardware Design']
MERGE (p)-[:HAS_EDUCATION]->(e);

// Occupation & Economic Context
MATCH (p:Person {id: 'person_placeholder'})
MERGE (o:Occupation {id: 'occupation_placeholder'})
SET o.employmentStatus = 'Employed',
    o.profession = 'Technology',
    o.incomeBracket = '50k-100k',
    o.workSchedule = 'Full-time'
MERGE (p)-[:HAS_OCCUPATION]->(o);

// Personality & Cognitive Style
MATCH (p:Person {id: 'person_placeholder'})
MERGE (ps:Personality {id: 'personality_placeholder'})
SET ps.introversion = 'Ambivert',
    ps.riskTolerance = 'Medium',
    ps.decisionMakingStyle = 'Analytical',
    ps.opennessToNewIdeas = 'High',
    ps.conflictStyle = 'Collaborative',
    ps.attentionToDetail = 'High'
MERGE (p)-[:HAS_PERSONALITY]->(ps);

// Communication Preferences
MATCH (p:Person {id: 'person_placeholder'})
MERGE (comm:Communication {id: 'communication_placeholder'})
SET comm.tonePreference = 'Casual',
    comm.responseLength = 'Concise',
    comm.structurePreference = 'Bullets',
    comm.toleranceForDebate = 'Medium',
    comm.humorPreference = 'Light'
MERGE (p)-[:HAS_COMMUNICATION_PREFS]->(comm);

// Goals & Motivations
MATCH (p:Person {id: 'person_placeholder'})
MERGE (g:Goals {id: 'goals_placeholder'})
SET g.shortTermGoals = ['Launch MVP'],
    g.longTermAspirations = ['Build sustainable product'],
    g.coreValues = ['Integrity', 'Growth'],
    g.definitionOfSuccess = 'User impact',
    g.primaryFears = ['Failure']
MERGE (p)-[:HAS_GOALS]->(g);

// Health & Physical Context
MATCH (p:Person {id: 'person_placeholder'})
MERGE (h:Health {id: 'health_placeholder'})
SET h.healthCondition = 'Good',
    h.disabilities = 'None disclosed',
    h.dietType = 'Mixed',
    h.sleepSchedule = '23:00-07:00',
    h.activityLevel = 'Moderate'
MERGE (p)-[:HAS_HEALTH]->(h);

// Technology Context
MATCH (p:Person {id: 'person_placeholder'})
MERGE (t:Technology {id: 'technology_placeholder'})
SET t.devicesUsed = ['Laptop', 'Phone'],
    t.operatingSystems = ['macOS', 'iOS'],
    t.internetLiteracy = 'Advanced',
    t.aiFamiliarity = 'High'
MERGE (p)-[:HAS_TECH_CONTEXT]->(t);

// Emotional Context
MATCH (p:Person {id: 'person_placeholder'})
MERGE (em:Emotional {id: 'emotional_placeholder'})
SET em.stressLevel = 'Medium',
    em.currentMood = 'Optimistic',
    em.majorLifeEvents = ['None disclosed'],
    em.stabilityPhase = 'Stable'
MERGE (p)-[:HAS_EMOTIONAL_STATE]->(em);

// Legal & Geographic Context
MATCH (p:Person {id: 'person_placeholder'})
MERGE (l:Legal {id: 'legal_placeholder'})
SET l.legalSystem = 'US',
    l.visaStatus = 'Citizen',
    l.taxRegime = 'US Federal/State'
MERGE (p)-[:HAS_LEGAL_CONTEXT]->(l);

// Privacy Boundaries
MATCH (p:Person {id: 'person_placeholder'})
MERGE (pr:Privacy {id: 'privacy_placeholder'})
SET pr.topicsToAvoid = ['Politics'],
    pr.sensitivityThreshold = 'High',
    pr.dataRetentionPreference = 'Do not store'
MERGE (p)-[:HAS_PRIVACY_PREFS]->(pr);
