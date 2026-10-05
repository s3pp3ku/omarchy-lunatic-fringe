# Playing Omarchy: Lunatic Fringe

Pilot the Omawing against the fictional Hater Fleet threatening agentic Omarchy.
The screensaver begins with autonomous flight. Topbar **Play** starts the score
right away; pressing a flight key or P takes control and loads your campaign.
The automatic idle screensaver stays silent.

## Controls

| Key | Action |
| --- | --- |
| W / Up | Forward thrust |
| S / Down | Reverse thrust; slows forward motion, then backs away |
| A / D / Left / Right | Turn |
| While piloting | Primary weapon autofires |
| Tab | Pause and open mission briefing |
| Enter | Accept next chapter; deploy the release at home in Mission 5 |
| H | Toggle home waypoint |
| U | Workshop within 145m of home |
| 1 / 2 / 3 / 4 | Buy weapon / hull / drive / credit magnet upgrades in workshop |
| Q | Cycle pulse, laser cannon, flamethrower, scatter, and piercing laser |
| 5 / 6 / 7 / 8 / 9 / 0 | Spend build points in workshop |
| T | Refund and reassign your build at home |
| F2 | Cycle Easy, Normal, Hard |
| M | Toggle sound and music |
| - / = | Lower / raise music volume |
| P | Toggle autopilot |
| Esc | Close briefing/workshop or exit and save |
| R, then Enter | Replay from briefing, keeping credits and upgrades |

Firing is automatic during manual flight; the old fire-key preference is ignored.

## Missions

1. **Let the Agents Cook:** clear Doomscroll drones from the mirror routes.
2. **Ship It Anyway:** recover signed agent packages from defeated carriers.
3. **Touch Grass, Sync Mirrors:** stay within 120m of each mirror for four
   uninterrupted seconds. Leaving resets that scan.
4. **The Comment Section:** destroy the armored flagship and its fan volleys.
5. **Merge to Main:** return home and press Enter to deploy the release.
6. **Clean the Pacman Cache:** recover six signed builds from poisoned caches.
7. **Hyprland Holds the Line:** restore all three mirror links under fire.
8. **Kernel Panic:** destroy the Dread Commenter siege flagship and restore
   the agent network.

Every completed chapter pauses for a briefing. Enter starts the next mission;
the final completion screen leads into free patrol. Old chapter drops do not
count toward the next chapter. The mission number and objective stay in the
corner; the full story is available in Tab.

Free patrol is an ongoing endgame, not an empty arena. It rotates Omarchy-themed
contracts for signed Pacman builds, Doomscroll drones, Hyprland mirrors and
shipping waves. Named Hater Fleet world bosses return about every 30–80 seconds;
the interval shortens as your kill count rises. Each flagship pays 1,200 credits
and drops a cache of orbs. Mirror scans move to a fresh node each time.

## Upgrades

Kills, pickups and mission completion award credits. Home repairs and refuels
for free. Open U there; the workshop pauses combat.

| Equipment | Successive upgrades | Costs |
| --- | --- | --- |
| Pacman Arsenal | Twin pulse, Tri-spread, Plasma lance, three plasma overclocks | 350 / 800 / 1500 / 2400 / 3600 / 5200 |
| Kernel Hardening | 135, 170, 205, 230, 255, 280 maximum hull | 300 / 650 / 1100 / 1900 / 3100 / 4800 |
| Hyprdrive | Six tiers of +55 forward/reverse acceleration | 250 / 550 / 950 / 1600 / 2600 / 4100 |
| Pacman Credit Magnet | Pull credit motes inward within 150 / 245 / 365 / 510m | 300 / 700 / 1450 / 2800 |

The workshop also awards build points: 3 at the start, 2 for each story
chapter, and 1 for each boss or free-patrol contract, up to 18 for the whole
save. Spend those points across six stats, each capped at level 6. Since all
stats share the same 18-point budget, you can fully specialize in three stats,
or spread points across a mixed build. **T** at home refunds your points so you
can try a new build. Old saves receive 18 available points on upgrade.

| Build stat | Effect |
| --- | --- |
| Pacman Damage | Boost damage on every shot |
| Bullet Storm | Add autofire barrels |
| Kernel Armor | Reduce incoming damage |
| Hyprdrive | Increase thrust and top speed |
| Relay Shields | Regenerate a shield pool and strengthen shield orbs |
| Cache Scanner | Increase loot drops and pull pickups inward from farther away |

Choose a weapon with **Q** while flying. The five modes are rapid pulse,
piercing laser, slow heavy laser cannon, wide scatter, and short-range
flamethrower. Defeated enemies can drop temporary rapid-fire, spread, flame,
and piercing buffs, plus health and shield orbs. Bosses always spill a cache.

Death/fuel depletion returns you home, keeping upgrades and objectives, with
a recovery fee of up to 100 credits and a short protective shield.

## Difficulty and collisions

Easy is the default. It lowers enemy population, damage, hull, firing rate and
projectile/movement speed. F2 changes difficulty and saves the choice.

| Setting | Incoming base damage | Hit protection | Respawn protection |
| --- | --- | --- | --- |
| Easy | 38% | 0.85 seconds | 8 seconds |
| Normal | 65% | 0.55 seconds | 6 seconds |
| Hard | 100% | 0.30 seconds | 4 seconds |

Ships bounce off asteroids and hostile ships. Asteroids block shots and break
under fire. The home relay is a safe docking area. Planets are background scenery.

## Audio, visuals and saves

Five weapon modes, stone/metal crashes, ricochets, explosions, buffs and pickups
use distinct synthesized clips. Manual flight has an original, three-minute
dark outrun score with pulsing analog-style bass, gated drums, and arpeggiated
minor synths. Topbar Play starts it immediately;
the automatic idle screensaver remains silent. M mutes all audio;
- and = adjust music volume. Audio caches are under `~/.cache/omavoid/`; music volume is saved in
`~/.config/omavoid/audio.json`.

The title fades to a corner label. The compact HUD shows the objective, credits,
hull, fuel and radar. Smooth camera lag, engine trails and white/blue/violet stars
communicate speed without a speedometer.

Campaign: `~/.local/state/omavoid/campaign.json`. Saves include objectives,
credits, equipment, mirror progress, difficulty, mute and pending briefings.
Manual play saves periodically, on upgrades and chapter completion, and on
normal exit/lock termination. Demo mode does not overwrite your pilot save.
Every resumed flight begins at home; positions and damaged enemies are not saved.
