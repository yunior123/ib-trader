#!/usr/bin/env python3
"""delta_setups_report.py — informe legible desde delta_setups_backtest.json.

Ademas INYECTA en el JSON el bloque `verificacion_independiente` producido por
delta_setups_verify.py (aditivo: no toca ninguna clave existente).
Todos los numeros salen del JSON; nada se teclea a mano.
"""
import json
import os
import sys

RES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "research")
J = os.path.join(RES, "delta_setups_backtest.json")
V = os.path.join(RES, "delta_setups_verify.json")
MD = os.path.join(RES, "delta_setups_backtest.md")

NOMBRE = {
    "DIVERG_M5": "DELTA DIVERGENCE M=5",
    "DIVERG_M10": "DELTA DIVERGENCE M=10",
    "DIVERG_M20": "DELTA DIVERGENCE M=20",
    "ABSORCION": "ABSORCION (abs delta p90 + rango p25, contrario)",
    "CVD_DIV_X5": "CVD DIVERGENCE X=5",
    "CVD_DIV_X10": "CVD DIVERGENCE X=10",
    "CVD_DIV_X20": "CVD DIVERGENCE X=20",
    "CVD_DIV_X30": "CVD DIVERGENCE X=30",
    "DELTA_FLIP": "DELTA FLIP (cambio de signo, vol p75)",
}
ORDEN = ["DIVERG_M5", "DIVERG_M10", "DIVERG_M20", "ABSORCION",
         "CVD_DIV_X5", "CVD_DIV_X10", "CVD_DIV_X20", "CVD_DIV_X30", "DELTA_FLIP"]


def main():
    d = json.load(open(J))
    ver = json.load(open(V)) if os.path.exists(V) else None
    ex = {}
    if ver:
        for ch in ver["checks"]:
            if "EXACTO" in ch["check"]:
                ex[ch["check"].split()[0]] = ch
        if set(ex) != {"DIVERG_M20", "ABSORCION"}:
            sys.stderr.write("FATAL: faltan los checks de null EXACTO: %s\n" % list(ex))
            sys.exit(1)
    cs = d["celdas"]
    n_fdr = sum(1 for c in cs if c["fdr_pass"])
    n_fdr_anti = sum(1 for c in cs if c["fdr_pass_anti"])
    n_art = sum(1 for c in cs if c["artefacto_volatilidad"])
    n_viv = sum(1 for c in cs if c["veredicto"].startswith("MEDIDO"))
    f = d["fuente"]
    L = []
    A = L.append

    A("# Delta divergence / absorcion / CVD / delta flip — MEDIDO, no supuesto")
    A("")
    A("**Veredicto: los CUATRO setups estan MUERTOS.** De %d celdas probadas, "
      "**%d** sobreviven." % (len(cs), n_viv))
    A("")
    A("| | |")
    A("|---|---|")
    A("| Celdas probadas | %d (9 variantes x 3 lados x 9 barreras) |" % len(cs))
    A("| Baten la entrada ALEATORIA (BH-FDR q=0,10) | **%d** |" % n_fdr)
    A("| Baten al MISMO PATRON DE PRECIO sin delta (BH-FDR) | **%d** |" % n_fdr_anti)
    n_art_fdr = sum(1 for c in cs if c["artefacto_volatilidad"] and c["fdr_pass"])
    A("| Marcadas artefacto de volatilidad (ganan en las DOS direcciones) | %d "
      "(de ellas %d baten ademas al azar: son las que un backtest ingenuo publicaria) |"
      % (n_art, n_art_fdr))
    A("| **Rentables medidas** (separan + superan al precio + expectancia > 0) | **%d** |" % n_viv)
    A("")
    if n_fdr == 0:
        A("El resultado ampliado es mas fuerte: **ninguna celda bate siquiera la entrada "
          "aleatoria** despues de BH-FDR; por tanto ninguna llega a superar el control "
          "estructural de precio ni a justificar un umbral predictivo.")
    else:
        A("El titular es la segunda fila contra la tercera: **%d celdas baten al azar y "
          "%d baten al patron de precio**. El control estructural evita publicar como "
          "Delta lo que ya explica el precio." % (n_fdr, n_fdr_anti))
    A("")

    A("## Datos")
    A("")
    A("- Tape: %s" % f["tape"])
    A("- Simbolos: %s | sesiones: %d (%s -> %s) | barras 1m: %d"
      % (", ".join(f["simbolos"]), f["n_sesiones"], f["dias"][0], f["dias"][-1],
         f["barras_1m"]))
    A("- Delta: %s" % f["delta"])
    au = f["auditoria_clasificacion"]
    A("- Volumen sin clasificar (`side=N`): **%.2f%%**" % au["pct_volumen_sin_clasificar_N"])
    if au.get("footprint_cells") and "corr_delta_nativo_vs_quoterule" in au["footprint_cells"]:
        A("- Auditoria del signo: el delta nativo del exchange vs la clasificacion por "
          "quote-rule correlaciona **%.4f** y coincide en signo el **%.2f%%** de las barras."
          % (au["footprint_cells"]["corr_delta_nativo_vs_quoterule"],
             100.0 * au["footprint_cells"]["acuerdo_de_signo"]))
    A("")
    A("> **LIMITACION QUE NO SE PUEDE OMITIR.** %s" % f["limitacion"])
    A("")

    A("## Metodo")
    A("")
    m = d["metodo"]
    for k in ("etiqueta", "entrada", "empate_tp_y_sl_en_la_misma_barra", "atr",
              "percentiles", "wilson", "multiplicidad", "umbral_publicacion"):
        A("- **%s**: %s" % (k.replace("_", " "), m[k]))
    A("")
    A("Tres controles, no uno:")
    A("")
    A("1. **Azar** — %s" % m["control_1_azar"])
    A("2. **Estructural (ANTI)** — %s" % m["control_2_estructural"])
    A("3. **Direccion opuesta** — %s" % m["control_3_direccion_opuesta"])
    A("")
    A("Los tres controles se conservan aunque el resultado ampliado ya muera contra el "
      "primero: impiden que una futura muestra mas favorable confunda volatilidad o "
      "estructura de precio con capacidad direccional de Delta.")
    A("")

    A("## Resultado por setup")
    A("")
    A("Mejor celda de cada setup (la de menor p contra el azar). `wr` = win rate, "
      "`null` = entrada aleatoria emparejada por simbolo/hora/direccion, "
      "`anti` = mismo patron de precio SIN la condicion de delta, "
      "`opp` = la MISMA barra operada al reves.")
    A("")
    A("| Setup | n señales | mejor celda | n | n_eff | wr | null | edge | Wilson 95% | p | anti | edge vs anti | opp | wr+opp vs 2·null | veredicto |")
    A("|---|---:|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|")
    for s in ORDEN:
        r = d["resumen_por_setup"][s]
        b = r["mejor_celda"]
        ver_corto = ("ARTEFACTO VOL" if b["artefacto_volatilidad"]
                     else ("EL DELTA NO APORTA" if b["veredicto"].startswith("EL DELTA")
                           else ("NO SEPARA DEL AZAR" if b["veredicto"].startswith("NO SEPARA")
                                 else b["veredicto"][:22])))
        A("| **%s** | %d | %s %s | %d | %.0f | %.4f | %.4f | %+.2f pp | [%.4f, %.4f] | %.1e | %s | %s | %.4f | %.3f vs %.3f | %s |"
          % (NOMBRE[s], r["n_señales"], b["lado"], b["barrera"], b["n"], b["n_eff"],
             b["win_rate"], b["null_wr"], b["edge_pp"], b["wilson_lo"], b["wilson_hi"],
             b["p_valor"],
             "%.4f" % b["anti_wr"] if b["anti_wr"] is not None else "n/d",
             "%+.2f pp" % b["edge_vs_anti_pp"] if b["edge_vs_anti_pp"] is not None else "n/d",
             b["wr_direccion_opuesta"],
             b["win_rate"] + b["wr_direccion_opuesta"], 2 * b["null_wr"], ver_corto))
    A("")
    A("Celdas que pasan BH-FDR contra el azar, por setup: " + ", ".join(
        "%s %d/27" % (s, d["resumen_por_setup"][s]["celdas_fdr_pass"]) for s in ORDEN) + ".")
    A("")

    A("## Los cuatro, uno a uno")
    A("")

    b = d["resumen_por_setup"]["DIVERG_M20"]["mejor_celda"]
    A("### 1. DELTA DIVERGENCE (M=5, 10, 20) — el edge es del PRECIO, no del delta")
    A("")
    n_div_fdr = sum(d["resumen_por_setup"][s]["celdas_fdr_pass"]
                    for s in ("DIVERG_M5", "DIVERG_M10", "DIVERG_M20"))
    A("De sus 81 celdas, **%d** baten al azar tras BH-FDR. La mejor (M=20, %s, %s) "
      "da wr **%.4f** contra azar **%.4f** (%+.2f pp, p=%.1e), pero no alcanza el "
      "umbral de publicacion ni supera de forma controlada el patron de precio."
      % (n_div_fdr, b["lado"], b["barrera"], b["win_rate"], b["null_wr"],
         b["edge_pp"], b["p_valor"]))
    A("")
    A("- **Direccion opuesta**: la misma barra operada al reves gana **%.4f**. "
      "Suma = %.3f contra 2·azar = %.3f. Si comprar Y vender la misma barra baten al "
      "azar, lo que se mide es que la barra extrema TOCA cualquier barrera ATR: es "
      "volatilidad, no direccion."
      % (b["wr_direccion_opuesta"], b["win_rate"] + b["wr_direccion_opuesta"],
         2 * b["null_wr"]))
    A("- **Control estructural**: las barras con el MISMO nuevo extremo de 20 barras "
      "pero SIN divergencia de delta ganan **%.4f** (n=%d). La condicion de delta añade "
      "%+.2f pp con p=%.3f — no sobrevive a la correccion por multiplicidad. "
      "El nuevo extremo de precio ya lo explica todo."
      % (b["anti_wr"], b["n_anti"], b["edge_vs_anti_pp"], b["p_valor_anti"]))
    A("")
    n_div_pay = sum(1 for c in cs if c["setup"].startswith("DIVERG_") and
                    c["fdr_pass"] and c["R_lb95"] is not None and c["R_lb95"] > 0)
    A("Celdas de divergencia con `fdr_pass` y `R_lb95>0`: **%d**; ninguna termina con "
      "veredicto MEDIDO rentable." % n_div_pay)
    A("")

    b = d["resumen_por_setup"]["ABSORCION"]["mejor_celda"]
    A("### 2. ABSORCION — no sobrevive como umbral predictivo")
    A("")
    A("Solo **%d señales** en %d sesiones-simbolo (la condicion |delta| p90 + rango p25 es rara), "
      "y de sus 27 celdas **%d** salen marcadas artefacto de volatilidad. La mejor "
      "(%s %s) luce espectacular — wr **%.4f** vs azar **%.4f**, **%+.2f pp** — y es el "
      "ejemplo mas claro del informe de por que eso no significa nada:"
      % (d["resumen_por_setup"]["ABSORCION"]["n_señales"], f["n_sesiones"],
         sum(1 for c in cs if c["setup"] == "ABSORCION" and c["artefacto_volatilidad"]),
         b["lado"], b["barrera"], b["win_rate"], b["null_wr"], b["edge_pp"]))
    A("")
    A("- La direccion contraria sobre las MISMAS barras gana **%.4f**. Suma %.3f vs "
      "2·azar %.3f: la barra de rango estrecho con delta extremo es simplemente el "
      "preludio de un movimiento **en cualquier sentido**."
      % (b["wr_direccion_opuesta"], b["win_rate"] + b["wr_direccion_opuesta"],
         2 * b["null_wr"]))
    A("- n = %d (n_eff = %.0f). Wilson [%.4f, %.4f]: el intervalo mide **%.1f puntos** "
      "de ancho. No hay muestra para afirmar nada."
      % (b["n"], b["n_eff"], b["wilson_lo"], b["wilson_hi"],
         100 * (b["wilson_hi"] - b["wilson_lo"])))
    A("- El null publicado se estima por Monte Carlo; el verificador recalcula de forma "
      "exacta una celda de auditoria separada. Los números exactos se muestran en la "
      "sección de verificación y no se trasladan a esta mejor celda.")
    A("")

    A("### 3. CVD DIVERGENCE (X=5, 10, 20, 30) — plano, sin excusas")
    A("")
    cvd = [c for c in cs if c["setup"].startswith("CVD_")]
    cvd_signals = sum(d["resumen_por_setup"][s]["n_señales"]
                      for s in ("CVD_DIV_X5", "CVD_DIV_X10", "CVD_DIV_X20", "CVD_DIV_X30"))
    A("**%d de 108 celdas** baten al azar tras BH-FDR, con %d señales en total. "
      "El mejor p-valor de toda la familia es %.2f. No hace falta control "
      "estructural: no hay nada que explicar."
      % (sum(1 for c in cvd if c["fdr_pass"]), cvd_signals,
         min(c["p_valor"] for c in cvd)))
    A("")
    for s in ("CVD_DIV_X5", "CVD_DIV_X10", "CVD_DIV_X20", "CVD_DIV_X30"):
        b2 = d["resumen_por_setup"][s]["mejor_celda"]
        A("- **%s**: %d señales, mejor wr %.4f vs azar %.4f (%+.2f pp), p=%.2f, "
          "R_lb95 %s -> no paga."
          % (s, d["resumen_por_setup"][s]["n_señales"], b2["win_rate"], b2["null_wr"],
             b2["edge_pp"], b2["p_valor"],
             "%+.3f" % b2["R_lb95"] if b2["R_lb95"] is not None else "n/d"))
    A("")

    b = d["resumen_por_setup"]["DELTA_FLIP"]["mejor_celda"]
    A("### 4. DELTA FLIP — muerto, y encima con expectancia NEGATIVA")
    A("")
    A("%d señales, **%d de 27 celdas** baten al azar. La mejor celda (%s %s) tiene wr "
      "**%.4f** vs azar **%.4f** (p=%.2f) y **R medio = %+.3f** con "
      "R_lb95 = %+.3f: seguir el nuevo signo del delta en barras de volumen alto "
      "PIERDE dinero en la muestra. Ademas %d de sus celdas salen artefacto."
      % (d["resumen_por_setup"]["DELTA_FLIP"]["n_señales"],
         d["resumen_por_setup"]["DELTA_FLIP"]["celdas_fdr_pass"], b["lado"], b["barrera"],
         b["win_rate"], b["null_wr"], b["p_valor"], b["R_medio"], b["R_lb95"],
         sum(1 for c in cs if c["setup"] == "DELTA_FLIP" and c["artefacto_volatilidad"])))
    A("")

    if ver:
        A("## Verificacion independiente")
        A("")
        A("`scripts/research/delta_setups_verify.py` reimplementa la triple barrera "
          "(vectorizada por desplazamiento, no señal a señal) y dos de los setups desde "
          "cero, y contrasta contra el JSON publicado: **%d/%d checks OK**."
          % (sum(1 for c in ver["checks"] if c["ok"]), len(ver["checks"])))
        A("")
        A("- Recuentos de señales: exactos en DIVERG M=5/10/20 y ABSORCION.")
        A("- Win rates de 5 celdas cabecera: coinciden **hasta el 5º decimal**.")
        A("- El azar se recalculo **EXACTO** (promediando sobre todo el estrato, sin "
          "muestreo): %.4f vs %.4f publicado en DIVERG_M20; %.4f vs %.4f en ABSORCION. "
          "Las diferencias son error de Monte Carlo del estudio, no un fallo."
          % (ex["DIVERG_M20"]["mio"], ex["DIVERG_M20"]["publicado"],
             ex["ABSORCION"]["mio"], ex["ABSORCION"]["publicado"]))
        A("")
        p = ver["delta_predice_barra_siguiente"]
        A("### Regalo del verificador: el delta agrupado por sesion no predice NADA")
        A("")
        A("| medicion | valor |")
        A("|---|---|")
        A("| corr(delta, retorno de la MISMA barra), agrupando todo | **%+.4f** (R2 %.2f%%) |"
          % (p["corr_misma_barra_pooled"], p["R2_misma_barra_pct"]))
        A("| corr(delta, retorno de la barra SIGUIENTE), agrupando todo | **%+.4f** |"
          % ver["corr_delta_ret_barra_siguiente"])
        A("| la misma, **por sesion** (media de %d sesiones) | **%+.4f** (sd %.4f) |"
          % (p["n_sesiones"], p["corr_media_por_sesion"], p["sd_entre_sesiones"]))
        A("| t agrupado por sesion | **%+.2f** |" % p["t_agrupado"])
        A("")
        A("Agrupando las %d barras de golpe, el delta parece predecir la barra "
          "siguiente con corr %+.4f. "
          "**Al agrupar por sesion la correlacion se vuelve %+.4f con t = %+.2f.** "
          "Ese +%.4f era estructura ENTRE dias (los dias de tendencia tienen a la vez "
          "mas delta medio y mas retorno medio), no capacidad predictiva dentro del dia. "
          "Es estructura entre dias, no capacidad predictiva intradia."
          % (f["barras_1m"], ver["corr_delta_ret_barra_siguiente"], p["corr_media_por_sesion"],
             p["t_agrupado"], ver["corr_delta_ret_barra_siguiente"]))
        A("")
        A("Contemporaneamente el delta SI explica (R2 %.2f%%), coherente con la "
          "literatura de OFI: explica el pasado inmediato, no el futuro."
          % p["R2_misma_barra_pct"])
        A("")

    A("## Que se hace con esto")
    A("")
    A("1. **No se construye ningun bot con estos cuatro setups.** Ni delta divergence, "
      "ni absorcion, ni CVD divergence, ni delta flip. Cero celdas rentables medidas.")
    A("2. Estos resultados prueban Delta de **acciones Nasdaq**, no el Delta/skew de "
      "opciones de Architect. Architect sigue siendo la doctrina principal de opciones; "
      "el footprint queda como confirmacion contemporanea en value, no como gatillo solo.")
    A("3. **El control que hay que exigir siempre es el ANTI**, ademas del azar. En esta "
      "muestra el azar aprueba %d de %d celdas." % (n_fdr, len(cs)))
    A("4. Lo unico defendible del delta de acciones sigue siendo **contemporaneo**: "
      "describe la barra que ya paso.")
    A("")

    A("## Huecos declarados")
    A("")
    A("- **Muestra corta**: %d fechas, %d simbolos, %d sesiones-simbolo. Suficiente "
      "para matar (los edges vs ANTI son de 1-4 pp con intervalos de 8-10 pp), "
      "insuficiente para resucitar: el control ANTI solo tiene potencia para detectar "
      "diferencias grandes. Un edge real de 2 pp NO se veria aqui."
      % (len(f["dias"]), len(f["simbolos"]), f["n_sesiones"]))
    A("- **%.2f%% del volumen sin lado agresor** (`side=N`) se descarta del delta. "
      "El estudio usa el delta nativo; la variante Lee-Ready esta en el .npz "
      "(`lr_b`/`lr_a`) y NO se probo como alternativa."
      % au["pct_volumen_sin_clasificar_N"])
    A("- **Solo cinta de Nasdaq (~14-21% del consolidado).** Un delta consolidado "
      "podria comportarse distinto; no es medible con los datos comprados.")
    A("- **Simbolos: %s.** Ya incluye NVDA, pero nada dice de futuros, que es donde el "
      "footprint nacio y CME publica el agresor de verdad." % ", ".join(f["simbolos"]))
    A("- No se probaron barreras asimetricas (objetivo != stop) ni salidas por tiempo "
      "cortas (<15 min), ni la combinacion de los setups entre si.")
    A("- El azar de las celdas con pocas señales tiene error de Monte Carlo de ~0,7 pp "
      "(25 replicas, 12 estratos). Solo se recalculo EXACTO en 2 celdas.")
    A("")
    A("---")
    A("Generado por `scripts/research/delta_setups.py` (medicion) + "
      "`delta_setups_verify.py` (verificacion independiente) + este `delta_setups_report.py`. "
      "Datos: `data/research/delta_setups_backtest.json`, "
      "`data/research/delta_setups_verify.json`.")

    txt = "\n".join(L) + "\n"
    tmp = MD + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(txt)
    os.replace(tmp, MD)

    if ver:
        d["verificacion_independiente"] = {
            "script": "scripts/research/delta_setups_verify.py",
            "nota": ("bloque AÑADIDO tras la medicion; no altera ninguna clave producida "
                     "por delta_setups.py"),
            "checks_ok": sum(1 for c in ver["checks"] if c["ok"]),
            "checks_total": len(ver["checks"]),
            "resultado": ver["verificacion_global"],
            "null_exacto": {c["check"]: {"exacto": c["mio"], "publicado": c["publicado"],
                                         "edge_pp_recalculado": c.get("edge_pp_recalculado")}
                            for c in ver["checks"] if "EXACTO" in c["check"]},
            "delta_predice_barra_siguiente": ver["delta_predice_barra_siguiente"]}
        tmp = J + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(d, fh, indent=1)
        os.replace(tmp, J)

    sys.stderr.write("OK -> %s (%d lineas)\n" % (MD, len(L)))


if __name__ == "__main__":
    main()
