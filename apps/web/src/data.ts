export type Lens = "org" | "faultlines" | "gaps";

export type PersonNode = {
  key: string;
  name: string;
  title: string;
  team: string;
  x: number;
  y: number;
  officialSize: number;
  actualSize: number;
  selected?: boolean;
};

export type Link = {
  source: string;
  target: string;
  strength: "strong" | "medium" | "weak";
};

export const people: PersonNode[] = [
  {
    key: "person:maya-chen",
    name: "Maya Chen",
    title: "Operations specialist",
    team: "operations",
    x: 50,
    y: 49,
    officialSize: 38,
    actualSize: 82,
    selected: true
  },
  {
    key: "person:alex-rivera",
    name: "Alex Rivera",
    title: "Payments director",
    team: "payments",
    x: 50,
    y: 16,
    officialSize: 68,
    actualSize: 54
  },
  {
    key: "person:priya-shah",
    name: "Priya Shah",
    title: "Payments lead",
    team: "payments",
    x: 32,
    y: 24,
    officialSize: 58,
    actualSize: 42
  },
  {
    key: "person:omar-haddad",
    name: "Omar Haddad",
    title: "Ledger lead",
    team: "ledger",
    x: 65,
    y: 55,
    officialSize: 58,
    actualSize: 44
  },
  {
    key: "person:lena-park",
    name: "Lena Park",
    title: "Ledger engineer",
    team: "ledger",
    x: 38,
    y: 64,
    officialSize: 46,
    actualSize: 34
  },
  {
    key: "person:theo-brooks",
    name: "Theo Brooks",
    title: "Ledger director",
    team: "ledger",
    x: 48,
    y: 82,
    officialSize: 68,
    actualSize: 20
  },
  {
    key: "person:nina-okafor",
    name: "Nina Okafor",
    title: "Customer success lead",
    team: "success",
    x: 18,
    y: 56,
    officialSize: 58,
    actualSize: 48
  },
  {
    key: "person:sam-wu",
    name: "Sam Wu",
    title: "CS partner",
    team: "success",
    x: 78,
    y: 30,
    officialSize: 46,
    actualSize: 28
  },
  {
    key: "person:ines-costa",
    name: "Ines Costa",
    title: "CS partner",
    team: "success",
    x: 82,
    y: 52,
    officialSize: 46,
    actualSize: 26
  },
  {
    key: "person:jon-bell",
    name: "Jon Bell",
    title: "CS partner",
    team: "success",
    x: 73,
    y: 72,
    officialSize: 46,
    actualSize: 24
  }
];

export const links: Link[] = [
  { source: "person:alex-rivera", target: "person:maya-chen", strength: "strong" },
  { source: "person:priya-shah", target: "person:maya-chen", strength: "strong" },
  { source: "person:maya-chen", target: "person:omar-haddad", strength: "strong" },
  { source: "person:maya-chen", target: "person:lena-park", strength: "strong" },
  { source: "person:omar-haddad", target: "person:lena-park", strength: "medium" },
  { source: "person:nina-okafor", target: "person:sam-wu", strength: "medium" },
  { source: "person:nina-okafor", target: "person:ines-costa", strength: "medium" },
  { source: "person:nina-okafor", target: "person:jon-bell", strength: "medium" },
  { source: "person:sam-wu", target: "person:ines-costa", strength: "weak" },
  { source: "person:sam-wu", target: "person:jon-bell", strength: "weak" },
  { source: "person:ines-costa", target: "person:jon-bell", strength: "weak" },
  { source: "person:alex-rivera", target: "person:priya-shah", strength: "medium" }
];

export const faultlineRows = [
  {
    id: "FL-001",
    modules: "payments-api -> ledger-worker",
    owners: "Alex Rivera / Theo Brooks",
    distance: "none within 4",
    severity: "12.0",
    tier: "no_path"
  },
  {
    id: "FL-002",
    modules: "identity-api -> audit-sink",
    owners: "Omar Haddad / unresolved",
    distance: "unknown",
    severity: "deferred",
    tier: "unsupported"
  }
];

export const gapRows = [
  {
    id: "G-001",
    path: "code-change -> missing-approval -> directive",
    expected: "approval",
    inferred: "2025-01-04 15:23 UTC",
    reason: "required sequence step missing"
  }
];

export const queryText = `CALL algo.MSpaths({
  sourceProperty: 'path_key',
  sourceValues: ['person:...'],
  targetProperty: 'path_key',
  targetValues: ['person:...'],
  relTypes: ['COMMUNICATES'],
  relDirection: 'both',
  maxLen: 4,
  pathCount: 3,
  resultLimit: 100,
  pairwise: true
}) YIELD path, pathWeight, pathCost
RETURN path, pathWeight, pathCost`;
