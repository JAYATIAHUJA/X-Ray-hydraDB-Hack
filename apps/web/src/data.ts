export type Lens = "org" | "faultlines" | "gaps";

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

export const queryTextByLens: Record<Lens, string> = {
  org: queryText,
  faultlines: `MATCH (source:Module)-[dependency:DEPENDS_ON]->(target:Module)
OPTIONAL MATCH (sourceOwner:Person)-[:OWNS]->(source)
OPTIONAL MATCH (targetOwner:Person)-[:OWNS]->(target)
MATCH path = shortestPath((sourceOwner)-[:COMMUNICATES*1..4]-(targetOwner))
RETURN source, target, dependency, path`,
  gaps: `MATCH (phantom:Phantom)
OPTIONAL MATCH (reply)-[:REPLIES_TO]->(phantom)
OPTIONAL MATCH (later)-[:PRECEDED_BY]->(phantom)
RETURN phantom, reply, later
ORDER BY phantom.canonical_key`
};
