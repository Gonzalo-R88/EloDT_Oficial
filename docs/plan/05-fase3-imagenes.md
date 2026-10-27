# Fase 3: Imágenes y contenido

Leer antes: `AGENTS.md`, `ESTADO.md` y las reglas generales de `00-INDICE.md`.
Tareas de este archivo: T3.1 a T3.8. **Argentina primero:** el primer post es el "Top 10 DTs en Argentina" (T3.1 + T3.2 + T3.3).

## Contexto necesario

- Existe `visualization.py` (matplotlib, 1600×900, paleta violeta/lila + celeste + blanco, fuentes Poppins y Anton en `assets/fonts/` con fallback DejaVu) con "Power Ranking de la Fecha" y "Duelo de Pizarras". **No se toca** hasta que las plantillas HTML lo igualen.
- Enfoque nuevo: plantillas HTML/CSS (Jinja2) renderizadas a PNG con Playwright/Chromium (ya es dependencia del scraper). Agregar `jinja2` a `requirements.txt`; Pillow ya viene con matplotlib.
- Sin escudos ni fotos de TM (copyright). Banderas como código de país en texto.
- Handle placeholder: `@AEP_Analitica`. Texto en español.
- Datos de entrada: `snapshots_elo` (T2.2), `ranking.py` (subidas/bajadas por ventana), `duel.py` (H2H y forma), `publicacion.py` (T0.5).

**Tamaños (variantes por plantilla):**

| Variante | Tamaño | Uso |
|---|---|---|
| `portrait` | 1080×1350 | LinkedIn e Instagram feed |
| `landscape` | 1600×900 | X y alternativa LinkedIn |
| `square` | 1080×1080 | Respaldo |
| `story` (opcional) | 1080×1920 | Stories |

**Formatos y datos:**

| Formato | Datos |
|---|---|
| Top 10 DTs en Argentina | Snapshot actual y anterior, club actual, PJ. DT cuyo **último club tiene `pais="Argentina"`**, activo y publicable. |
| Subidas y bajadas | Partidos de la ventana (7 días hasta `semana_fin`), mínimo 15 PJ; interinos con ≥5 PJ etiquetados. Reusa `ranking.py`. |
| Duelo de la semana | DTs que se enfrentaron esa semana con mayor ELO combinado; historial entre ellos; mini-gráfico de ELO (SVG). Reusa `duel.py`. |
| Top 10 global | Snapshots, todos los publicables. |
| DT revelación | <2 años de carrera, ≥15 PJ, mayor suba en 90 días. |
| Top por país/liga (rotativo) | Snapshots + país del club actual. |

**Rotación sugerida:** se generan todos los formatos cada lunes y se marca uno como "sugerido de la semana" por semana ISO módulo 4: 0 → Top Argentina, 1 → Subidas y bajadas, 2 → Duelo, 3 → Top global.

---

## T3.1: Capa de datos de contenido

- **Tipo:** ⚙️.
- **Depende de:** T2.2, T0.6.
- **Archivos:** `content.py` (sin matplotlib ni Playwright), `tests/test_content.py` (SQLite).
- **Funciones:** `top_n(session, semana_fin, n, pais=None)`, `movers(session, semana_fin, dias=7, pais=None)`, `duelo_de_la_semana(session, semana_fin)`, `revelacion(session, semana_fin)`, `top_por_pais(session, semana_fin, pais, n)`. Todas devuelven dataclasses con los campos que necesita cada plantilla (nombre, club, ELO, delta, PJ, etiqueta, ranking previo, partidos de la semana).
- **Reglas:** filtran por `publicable`; el interino (<15 PJ, ≥5 PJ) solo aparece en `movers`, con etiqueta; el ▲▼ de `top_n` compara con el snapshot anterior (si no existe, sin flecha).
- **Aceptación:** tests con casos: DT con 14 PJ excluido del Top 10; interino con 8 PJ presente en `movers` con etiqueta; DT inactivo excluido; cambio de posición correcto entre snapshots; `pais="Argentina"` filtra bien.

## T3.2: Infraestructura de render HTML

- **Tipo:** ⚙️.
- **Depende de:** —.
- **Archivos:** `templates/base.css` (variables de marca, `@font-face` locales para Poppins y Anton), `templates/_macros.html`, `render_html.py`, `requirements.txt` (+`jinja2`), `tests/test_render_html.py`.
- **Pasos:** `render_png(plantilla, contexto, variante, salida)` con Jinja2 + Playwright sync (`viewport` = tamaño de la variante, `device_scale_factor=1`, `page.screenshot`); espera a que las fuentes carguen; imports perezosos de Playwright (los tests no deben fallar si falta Chromium: marcar con `skipif`).
- **Aceptación:** una plantilla de prueba produce un PNG con dimensiones **exactas** de 1080×1350 y 1600×900 (verificado con Pillow); las fuentes cargan desde `assets/fonts/`; el módulo funciona sin DB.

## T3.3: Plantilla Top 10

- **Tipo:** ⚙️ + 👤 (aprobación visual).
- **Depende de:** T3.1, T3.2.
- **Archivos:** `templates/top10.html` (+ CSS por variante), `tests/test_templates.py`.
- **Contenido:** título (por ejemplo "Top 10 DTs de Argentina"), semana, ranking 1-10 con nombre, club, ELO (entero), ▲▼ y delta de posición, etiqueta "provisorio" si corresponde, pie con "N partidos analizados" y el handle.
- **Aceptación:** sin desbordes con nombres de 40 caracteres y ELO de 4 dígitos (test con datos extremos); tamaño del PNG <1,5 MB; contraste legible; las tres variantes (`portrait`, `landscape`, `square`) salen correctas.
- **Parada humana:** el usuario aprueba el diseño del primer Top 10 con datos reales de Argentina.

## T3.4: Plantilla Subidas y bajadas

- **Tipo:** ⚙️.
- **Depende de:** T3.1, T3.2.
- **Archivos:** `templates/movers.html`.
- **Contenido:** 5 subidas y 5 bajadas con club, delta de ELO, ELO actual y resultados de la semana; interinos con etiqueta.
- **Aceptación:** mismos criterios que T3.3.

## T3.5: Plantilla Duelo

- **Tipo:** ⚙️.
- **Depende de:** T3.1, T3.2.
- **Archivos:** `templates/duelo.html` (mini-gráfico de ELO como SVG inline).
- **Contenido:** dos DTs, ELO, forma (últimos 5), historial entre ellos y mini-gráfico de ELO de los últimos meses (desde `snapshots_elo`).
- **Aceptación:** mismos criterios que T3.3; el SVG se ve bien con 0 y con 52 puntos.

## T3.6: Plantilla Revelación

- **Tipo:** ⚙️.
- **Depende de:** T3.1, T3.2.
- **Archivos:** `templates/revelacion.html`.
- **Contenido:** DT revelación con ELO actual, suba en 90 días, PJ y etapa de carrera.
- **Aceptación:** mismos criterios que T3.3.

## T3.7: Textos sugeridos

- **Tipo:** ⚙️.
- **Depende de:** T3.1.
- **Archivos:** `captions.py`, `tests/test_captions.py`.
- **Contenido:** por formato, tres textos en español (LinkedIn más largo; X ≤ 280 caracteres incluyendo hashtags; Instagram) y un texto alternativo por imagen. Plantillas deterministas con datos reales (sin LLM). Incluir siempre la aclaración "ELO propio calculado con datos de Transfermarkt" y el handle.
- **Aceptación:** tests de longitud (X ≤ 280), de que no quedan placeholders sin reemplazar y de que los números del texto coinciden con los de la imagen.

## T3.8: Subcomando `render`

- **Tipo:** ⚙️.
- **Depende de:** T3.3 a T3.7, T2.5.
- **Archivos:** `scripts/weekly_run.py` (`render`), `tests/test_weekly_run.py`.
- **Comportamiento:** crea `data/output/YYYY-Www/` con `top10_argentina_{portrait,landscape,square}.png`, `movers_*`, `duelo_*`, `top10_global_*`, `revelacion_*`, `post.md` (textos de T3.7 y formato sugerido) y `summary.json`; idempotente por semana; si un formato no tiene datos suficientes, lo omite y lo registra en `summary.json` (no falla toda la corrida); marca el formato "sugerido de la semana" (semana ISO módulo 4).
- **Aceptación:** una corrida real genera el paquete completo con datos reales; una segunda corrida no duplica ni rompe; `summary.json` lista formatos generados y omitidos con motivo.
