PRAGMA foreign_keys=ON;
CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE sources(id TEXT PRIMARY KEY,path TEXT UNIQUE NOT NULL,sha256 TEXT,size_bytes INTEGER,family TEXT NOT NULL,kind TEXT,disposition TEXT NOT NULL,note TEXT);
CREATE TABLE places(id TEXT PRIMARY KEY,level TEXT NOT NULL,parent_id TEXT REFERENCES places(id),name TEXT NOT NULL,name_key TEXT NOT NULL,identity_status TEXT NOT NULL DEFAULT 'source_claim');
CREATE INDEX place_parent_name ON places(parent_id,name_key,level);
CREATE TABLE aliases(place_id TEXT REFERENCES places(id),alias TEXT,name_key TEXT,source_id TEXT REFERENCES sources(id),kind TEXT,PRIMARY KEY(place_id,name_key,source_id,kind));
CREATE INDEX alias_lookup ON aliases(name_key);
CREATE TABLE place_claims(place_id TEXT REFERENCES places(id),source_id TEXT REFERENCES sources(id),locator TEXT,claimed_level TEXT,PRIMARY KEY(place_id,source_id,claimed_level));
CREATE TABLE parent_claims(child_id TEXT REFERENCES places(id),parent_id TEXT REFERENCES places(id),relation TEXT,source_id TEXT REFERENCES sources(id),locator TEXT,valid_from TEXT,valid_to TEXT,PRIMARY KEY(child_id,parent_id,relation,source_id));
CREATE TABLE place_codes(place_id TEXT REFERENCES places(id),scheme TEXT,value TEXT,source_id TEXT REFERENCES sources(id),locator TEXT,PRIMARY KEY(place_id,scheme,value,source_id));
CREATE TABLE leg_districts(id TEXT PRIMARY KEY,jurisdiction TEXT NOT NULL,jurisdiction_key TEXT NOT NULL,designation TEXT NOT NULL);
CREATE TABLE leg_jurisdiction_claims(leg_id TEXT REFERENCES leg_districts(id),place_id TEXT REFERENCES places(id),source_id TEXT REFERENCES sources(id),locator TEXT,PRIMARY KEY(leg_id,place_id,source_id));
CREATE TABLE leg_memberships(id TEXT PRIMARY KEY,place_id TEXT REFERENCES places(id),leg_id TEXT REFERENCES leg_districts(id),source_id TEXT REFERENCES sources(id),locator TEXT,scope TEXT,valid_from TEXT,valid_to TEXT,status TEXT NOT NULL,candidates_json TEXT,raw_json TEXT);
CREATE INDEX membership_place ON leg_memberships(place_id,leg_id);
CREATE TABLE representatives(id TEXT PRIMARY KEY,name TEXT NOT NULL,name_key TEXT NOT NULL);
CREATE TABLE representative_terms(id TEXT PRIMARY KEY,representative_id TEXT REFERENCES representatives(id),leg_id TEXT REFERENCES leg_districts(id),source_id TEXT REFERENCES sources(id),locator TEXT,term_label TEXT,start_year INTEGER,end_year INTEGER,valid_from TEXT,valid_to TEXT,raw_json TEXT);
CREATE TABLE deos(id TEXT PRIMARY KEY,name TEXT NOT NULL,name_key TEXT UNIQUE NOT NULL);
CREATE TABLE deo_aliases(deo_id TEXT REFERENCES deos(id),alias TEXT,name_key TEXT,source_id TEXT REFERENCES sources(id),PRIMARY KEY(deo_id,name_key,source_id));
CREATE TABLE deo_leg_claims(id TEXT PRIMARY KEY,deo_id TEXT REFERENCES deos(id),leg_id TEXT REFERENCES leg_districts(id),source_id TEXT REFERENCES sources(id),locator TEXT,valid_from TEXT,valid_to TEXT,amount_pesos INTEGER,fiscal_year INTEGER,budget_stage TEXT,status TEXT,raw_json TEXT);
CREATE TABLE deo_place_claims(id TEXT PRIMARY KEY,deo_id TEXT REFERENCES deos(id),place_id TEXT REFERENCES places(id),source_id TEXT REFERENCES sources(id),locator TEXT,relation TEXT,status TEXT,raw_json TEXT);
CREATE TABLE observations(id TEXT PRIMARY KEY,source_id TEXT REFERENCES sources(id),locator TEXT,kind TEXT,raw_json TEXT NOT NULL);
CREATE TABLE issues(id TEXT PRIMARY KEY,kind TEXT,entity_id TEXT,source_id TEXT REFERENCES sources(id),locator TEXT,detail_json TEXT NOT NULL);
CREATE VIEW leg_membership_review AS
 SELECT m.place_id,COUNT(DISTINCT m.leg_id) AS district_claims,COUNT(DISTINCT s.family) AS source_families,
 CASE WHEN COUNT(DISTINCT m.leg_id)>1 THEN 'conflict'
      WHEN COUNT(DISTINCT s.family)>1 THEN 'multiple_local_claims'
      ELSE 'single_source_claim' END AS status
 FROM leg_memberships m JOIN sources s ON s.id=m.source_id
 WHERE m.place_id IS NOT NULL AND m.status='located_source_claim' GROUP BY m.place_id;
CREATE VIEW shared_names AS
 SELECT name_key,COUNT(DISTINCT place_id) AS candidate_places FROM aliases GROUP BY name_key HAVING COUNT(DISTINCT place_id)>1;
CREATE VIEW geographic_paths AS
 WITH RECURSIVE paths(id,path,depth) AS (
 SELECT id,name,0 FROM places WHERE parent_id IS NULL
 UNION ALL SELECT p.id,paths.path || ' > ' || p.name,depth+1 FROM places p JOIN paths ON p.parent_id=paths.id)
 SELECT * FROM paths;
CREATE VIEW province_region_review AS
 SELECT child_id AS province_id,COUNT(DISTINCT parent_id) AS region_claims,
 CASE WHEN COUNT(DISTINCT parent_id)=1 THEN MIN(parent_id) END AS unambiguous_region_id
 FROM parent_claims WHERE relation='region_membership' GROUP BY child_id;
