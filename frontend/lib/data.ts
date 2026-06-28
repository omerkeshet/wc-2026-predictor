import { promises as fs } from "fs";
import path from "path";
import type {
  MatchesPayload,
  RatingsPayload,
  TournamentPayload,
  Meta,
} from "./types";

const DATA_DIR = path.join(process.cwd(), "public", "data");

async function readJson<T>(filename: string): Promise<T> {
  const raw = await fs.readFile(path.join(DATA_DIR, filename), "utf-8");
  return JSON.parse(raw) as T;
}

export const loadMatches = () => readJson<MatchesPayload>("matches.json");
export const loadRatings = () => readJson<RatingsPayload>("ratings.json");
export const loadTournament = () => readJson<TournamentPayload>("tournament.json");
export const loadMeta = () => readJson<Meta>("meta.json");
export const loadR32 = () => readJson<MatchesPayload>("r32.json");
