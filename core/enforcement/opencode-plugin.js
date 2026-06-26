// Determinism protocol enforcement for OpenCode. Mirrors the Claude/Copilot/VS Code
// hooks: a commit gate (block `git commit` when the repo's `verify` verb fails) + a
// nudge to use the deterministic front door. Plain JS, no build. Auto-loaded from
// ~/.config/opencode/plugin/ (symlinked there by `agentsync apply`).
//
// Runner-agnostic: detects whichever task runner the repo uses (mise/make/just/npm).
// Fails OPEN everywhere it can't act (no runner, no `verify` verb, infra error) so it
// can never wedge commits. Only a real verify failure blocks.
export const Determinism = async ({ $, directory }) => {
  const sh = (strings, ...v) => $(strings, ...v).cwd(directory).nothrow().quiet()

  // Returns { run, has } for the detected runner, or null if none is present.
  const detect = async () => {
    const has = async (f) => (await sh`sh -c 'test -e ${f}'`).exitCode === 0
    const ok = async (c) => (await sh`sh -c 'command -v ${c}'`).exitCode === 0
    if ((await has("mise.toml") || await has(".mise.toml")) && await ok("mise"))
      return { id: "mise", run: "mise run", hasVerb: async () => /(^|\n)verify(\s|$)/.test(String((await sh`mise tasks`).stdout)) }
    if ((await has("Makefile") || await has("makefile") || await has("GNUmakefile")) && await ok("make"))
      return { id: "make", run: "make", hasVerb: async () => (await sh`make -n verify`).exitCode === 0 }
    if ((await has("justfile") || await has("Justfile")) && await ok("just"))
      return { id: "just", run: "just", hasVerb: async () => (await sh`just --show verify`).exitCode === 0 }
    if (await has("package.json") && await ok("npm"))
      return { id: "npm", run: "npm run --silent", hasVerb: async () => (await sh`node -e 'process.exit((((require("./package.json").scripts)||{}).verify)?0:1)'`).exitCode === 0 }
    return null
  }

  return {
    // Commit gate.
    "tool.execute.before": async (input, output) => {
      if (input.tool !== "bash") return
      const cmd = String(output.args?.command ?? "")
      if (!/\bgit\s+commit\b/.test(cmd)) return
      let block = false, detail = ""
      try {
        const r = await detect()
        if (!r) return                                           // no front door -> allow
        if (!(await r.hasVerb())) return                         // no verify verb -> allow
        const res = await sh`sh -c ${`${r.run} verify`}`
        if (res.exitCode !== 0) { block = true; detail = String(res.stdout) + String(res.stderr) }
      } catch {
        return                                                   // infra error -> fail open
      }
      if (block) throw new Error(`Commit blocked: \`verify\` failed — fix before committing.\n${detail}`)
    },
    // Discoverability nudge (OpenCode has no clean session-start injection; push to the
    // system prompt instead). experimental.* may change; unknown hooks are ignored, so
    // this degrades safely.
    "experimental.chat.system.transform": async (_input, output) => {
      output.system.push(
        "Determinism protocol: prefer this repo's deterministic task verbs (make/mise/just/npm) over ad-hoc shell. If the repo has none, scaffold with `scaffold-determinism`. Repeatable work belongs in a script/task, not re-derived each time.",
      )
    },
  }
}
