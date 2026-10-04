# Playing Omarchy: Lunatic Fringe

Pilot the Omawing against the fictional Hater Fleet threatening agentic Omarchy.
The screensaver begins with silent autonomous flight. Press a flight key or P to
load your saved campaign at home.

## Controls

| Key | Action |
| --- | --- |
| W / Up | Forward thrust |
| S / Down | Reverse thrust; slows forward motion, then backs away |
| A / D / Left / Right | Turn |
| Left Ctrl | Fire |
| Tab | Pause and open mission briefing |
| Enter | Accept next chapter; deploy the release at home in Mission 5 |
| H | Toggle home waypoint |
| U | Workshop within 145m of home |
| 1 / 2 / 3 | Buy weapon / hull / drive upgrades in workshop |
| F2 | Cycle Easy, Normal, Hard |
| M | Toggle sound |
| P | Toggle autopilot |
| Esc | Close briefing/workshop or exit and save |
| R, then Enter | Replay from briefing, keeping credits and upgrades |

`~/.config/omavoid/controls.json` can override firing:

```json
{"fire": ["Control_L"]}
```

For a Space alternative, use `{"fire":["Control_L","space"]}`.

## Missions

1. **Let the Agents Cook:** defeat five Doomscroll drones.
2. **Ship It Anyway:** defeat package carriers and recover four fresh gold drops.
3. **Touch Grass, Sync Mirrors:** stay within 120m of each mirror for four
   uninterrupted seconds. Leaving resets that scan.
4. **The Comment Section:** destroy the armored flagship and its fan volleys.
5. **Merge to Main:** return home and press Enter to deploy the release.

Every completed chapter pauses for a briefing. Enter starts the next mission;
the final completion screen leads into free patrol. Old chapter drops do not
count toward the next chapter. The mission number and objective stay in the
corner; the full story is available in Tab.

## Upgrades

Kills, pickups and mission completion award credits. Home repairs and refuels
for free. Open U there; the workshop pauses combat.

| Equipment | Successive upgrades | Costs |
| --- | --- | --- |
| Pacman Arsenal | Twin pulse, Tri-spread, Plasma lance | 350 / 800 / 1500 |
| Kernel Hardening | 135, 170, 205 maximum hull | 300 / 650 / 1100 |
| Hyprdrive | +55, +110, +165 forward/reverse acceleration | 250 / 550 / 950 |

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

Four distinct weapons, stone/metal crashes, ricochets, explosions and interface
cues use 45 original synthesized clips. Autopilot stays silent; M mutes manual
play. Sound cache: `~/.cache/omavoid/sfx/v2/`.

The title fades to a corner label. The compact HUD shows the objective, credits,
hull, fuel and radar. Smooth camera lag, engine trails and white/blue/violet stars
communicate speed without a speedometer.

Campaign: `~/.local/state/omavoid/campaign.json`. Saves include objectives,
credits, equipment, mirror progress, difficulty, mute and pending briefings.
Manual play saves periodically, on upgrades and chapter completion, and on
normal exit/lock termination. Demo mode does not overwrite your pilot save.
Every resumed flight begins at home; positions and damaged enemies are not saved.
