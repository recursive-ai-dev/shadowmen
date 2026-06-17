# Shadow Men: Technical Design Specification (Reasoning Topology)

## Phase 1: Skeleton Creation (SoT) - Reasoning Topology Blueprint

The simulation will move from simple reactive agents to a Reasoning Topology where behaviors are driven by heritable traits, environmental context, and social signals.

### 1. Kin Selection (Altruism)
- **Concept**: Agents will prioritize the survival of closely related individuals (shared genetic markers).
- **Mechanism**: Alarm calls. When a predator is detected, an agent can "signal" others. This increases the survival of the kin but may increase the caller's visibility/risk.
- **Traits**: `altruism_score` (0-1), `signal_radius` (range).

### 2. Resource Scarcity Logic
- **Concept**: Introduction of an "Energy" or "Satiety" meter.
- **Mechanism**: Movement and actions consume energy. Energy is replenished by "grazing" (staying idle on specific window biomes) or social interaction (sharing).
- **Traits**: `metabolism_rate`, `energy_storage_cap`.

### 3. Environmental Hazard Interaction (Window Biomes)
- **Concept**: Windows are no longer just platforms but have "Biomes" (e.g., Cold, Warm, Resource-Rich).
- **Mechanism**: Window title/class detection via `wmctrl` to assign biomes.
  - *Terminal*: "Hardened" biome (high friction, low resource).
  - *Browser*: "Information-Rich" biome (high resource, high risk of "falling" due to updates).
- **Traits**: `biome_affinity`.

---

## Phase 2: Recursive Decomposition (ToT) - Implementation Paths

### Feature: Kin Selection (Altruism)
1.  **Path A: Purely Heritable (Selected)**: `altruism` gene determines the probability of signaling. Simple, low cost, high emergence potential via group selection.
2.  **Path B: Neural Net Trait**: Small MLP takes (predator_dist, kin_dist) and outputs signal decision. *Cost*: High. *Stability*: Low (overfitting).
3.  **Path C: Tit-for-Tat (Social Memory)**: Agents remember who helped them. *Cost*: Medium (requires memory structures).

*Decision*: Path A for minimal CPU impact and clear evolutionary pressure.

### Feature: Resource Scarcity
1.  **Path A: Constant Decay (Selected)**: Energy decreases every tick. Requires "foraging" (idling on windows).
2.  **Path B: Action-Based Decay**: Jumping/Climbing costs more than Walking. *Cost*: Minimal.
3.  **Path C: Predator Scavenging**: Predators drop "food" on kill.

*Decision*: Path A + B for deterministic metabolic pressure.

---

## Phase 3: Logic Hardening (wmctrl)

**Problem**: Race conditions when window geometries change during a tick, leading to agents "floating" or "trapped" in old geometry.

**Proposed Solution**:
- **Deterministic Event Loop**: Window snapshots are taken once at the start of a logical "frame" and cached.
- **Interpolation**: Use a secondary buffer to detect rapid movements and "snap" agents or initiate "re-grounding" logic.

---

## Phase 4: Optimization (Token Complexity & Cairo)

**Genome Optimization**:
- Use vectorization for Gaussian mutations if population > 100.
- Flatten trait accessors to avoid `getattr` in hot loops.

**Rendering Optimization**:
- **Renderer Caching**: Reuse `CharacterRenderer` instances per agent.
- **Dirty Rectangles**: Only redraw regions where agents moved (though full-screen transparent overlays usually require full clear, we can optimize the path creation).
