import math

# Portée maximale en pixels (vidéo 480x360, grimpeur à ~2m de la caméra)
# Un bras tendu ≈ 90cm ≈ 210px ; une jambe ≈ 80cm ≈ 190px
PORTEE_MAIN = 220
PORTEE_PIED = 190
MARGE_MIN   = 20    # distance minimale (prise déjà sous le membre)


def trouver_prises_par_membre(membres, prises):
    """
    Pour un grimpeur aveugle : retourne la prise la plus proche dans la bonne
    direction pour chaque membre.

    Deux passes :
      1. Dans la portée physique normale (PORTEE_MAIN / PORTEE_PIED).
      2. Si rien trouvé, recherche sans limite de distance (pour assurer la
         progression quand le grimpeur a atteint toutes les prises proches).

    Paramètres
    ----------
    membres : dict  { 'main_droite' | 'main_gauche' | 'pied_droit' | 'pied_gauche'
                      → (x, y) | None }
    prises  : list  [ {'coords': (cx, cy), 'usage': 'Mains+Pieds'|'Pieds'} ]

    Retourne
    --------
    dict  membre → (px, py) | None
    """
    suggestions = {k: None for k in membres}

    # Hauteur moyenne des mains → les pieds ne peuvent pas monter au-dessus
    ys_mains = [membres[k][1] for k in ('main_droite', 'main_gauche')
                if membres.get(k)]
    y_mains = sum(ys_mains) / len(ys_mains) if ys_mains else None

    for membre, pos in membres.items():
        if pos is None:
            continue

        mx, my   = pos
        est_main = 'main' in membre
        usage_ok = 'Mains+Pieds' if est_main else None
        portee   = PORTEE_MAIN if est_main else PORTEE_PIED

        # Passe 1 : portée normale ; passe 2 : sans limite (progression garantie)
        for portee_max in (portee, float('inf')):
            meilleur       = None
            meilleure_dist = float('inf')

            for p in prises:
                px, py = p['coords']

                if usage_ok is not None and p.get('usage', 'Mains+Pieds') != usage_ok:
                    continue

                dist = math.hypot(px - mx, py - my)

                if dist < MARGE_MIN or dist > portee_max:
                    continue

                if est_main:
                    # Mains : viser uniquement des prises au-dessus ou au niveau
                    if py > my + 60:
                        continue
                else:
                    # Pieds : rester sous le niveau des mains
                    if y_mains is not None and py < y_mains - 30:
                        continue

                if dist < meilleure_dist:
                    meilleure_dist = dist
                    meilleur = (px, py)

            if meilleur is not None:
                break  # passe 1 suffisante, inutile d'élargir

        suggestions[membre] = meilleur

    return suggestions


# ── Compatibilité avec l'ancien appel (VideoWorker avant refacto) ─────────────
def trouver_prochaine_prise(main_droite, main_gauche, prises_coords):
    prises   = [{'coords': c, 'usage': 'Mains'} for c in prises_coords]
    membres  = {'main_droite': main_droite, 'main_gauche': main_gauche,
                'pied_droit': None, 'pied_gauche': None}
    sug      = trouver_prises_par_membre(membres, prises)
    resultats = []
    for k in ('main_droite', 'main_gauche'):
        if sug[k] and membres[k]:
            d = math.hypot(sug[k][0] - membres[k][0], sug[k][1] - membres[k][1])
            resultats.append((d, sug[k], membres[k]))
    if resultats:
        resultats.sort()
        return resultats[0][1], resultats[0][2]
    return None, None
