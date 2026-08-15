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
