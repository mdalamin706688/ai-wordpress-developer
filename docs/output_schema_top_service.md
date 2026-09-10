# TOP + Service predefined rules (enforced)

## How it works (simple)

1. **Hearing** = facts  
2. **Classic prompts** = how to write JSON  
3. **TOP / Service tabs** = section checklist  
4. After AI writes → system **checks** required sections are covered  
5. WordPress draft always includes **home + service + menu + access + contact**  
6. Each of home/service carries structured `sections` matching the tab checklist  

## Required coverage

### TOP (`page=top`)
hero, about, concept, menu, access, reservation  
(+ greeting / reviews only if hearing has them)

### Service (`page=service`)
hero, services (every menu name), reservation  

Missing required section → `SECTION_GAP` → draft blocked until fixed.

## Pages in package

`home → service → menu → access → contact` (all `draft`, never auto-publish)
