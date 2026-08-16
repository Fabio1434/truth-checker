/* Presentation demo layer.
   It keeps the normal Truth Checker UI and workflow, but supplies deterministic
   VRAI/FAUX results when TRUTHCHECKER_DEMO is enabled in the page configuration.
   It never changes the real backend or evidence engine.
*/
(() => {
  "use strict";

  // Demo is enabled by the hosting page only when explicitly requested.
  // Set window.TRUTHCHECKER_DEMO = true before loading this file.
  if (window.TRUTHCHECKER_DEMO !== true) return;

  const realFetch = window.fetch.bind(window);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const makeResult = (mode, content) => {
    const isTrue = mode === "true";
    const claim = content || (isTrue
      ? "L'eau bout à 100 °C au niveau de la mer."
      : "La Terre possède deux lunes naturelles.");

    const sources = isTrue
      ? [
          { title: "National Institute of Standards and Technology", url: "https://www.nist.gov/", domain: "nist.gov", stance: "confirme", excerpt: "Références scientifiques sur les propriétés thermodynamiques de l'eau.", source_type: "official", authority_score: 98, independence: 94, relevance: 97, freshness: "actuel" },
          { title: "Encyclopaedia Britannica — Water", url: "https://www.britannica.com/science/water", domain: "britannica.com", stance: "confirme", excerpt: "L'eau atteint son point d'ébullition à 100 °C à pression atmosphérique normale.", source_type: "encyclopedia", authority_score: 92, independence: 90, relevance: 96, freshness: "actuel" },
          { title: "U.S. Geological Survey — Water", url: "https://www.usgs.gov/special-topics/water-science-school", domain: "usgs.gov", stance: "confirme", excerpt: "Ressources scientifiques de référence sur l'eau et ses propriétés.", source_type: "official", authority_score: 96, independence: 93, relevance: 94, freshness: "actuel" }
        ]
      : [
          { title: "NASA — Moon", url: "https://science.nasa.gov/moon/", domain: "nasa.gov", stance: "contredit", excerpt: "La Lune est le satellite naturel de la Terre.", source_type: "official", authority_score: 99, independence: 96, relevance: 99, freshness: "actuel" },
          { title: "Encyclopaedia Britannica — Moon", url: "https://www.britannica.com/place/Moon", domain: "britannica.com", stance: "contredit", excerpt: "La Lune est le seul satellite naturel permanent de la Terre.", source_type: "encyclopedia", authority_score: 92, independence: 91, relevance: 98, freshness: "actuel" },
          { title: "European Space Agency — Moon", url: "https://www.esa.int/Science_Exploration/Human_and_Robotic_Exploration/Exploration/Moon", domain: "esa.int", stance: "contredit", excerpt: "La Lune est le satellite naturel de notre planète.", source_type: "official", authority_score: 98, independence: 95, relevance: 98, freshness: "actuel" }
        ];

    return {
      verdict: isTrue ? "vrai" : "faux",
      score: isTrue ? 96 : 98,
      headline_claim: claim,
      summary: isTrue
        ? "L'affirmation est cohérente avec les références scientifiques disponibles dans ce scénario de présentation."
        : "L'affirmation est contredite par les références astronomiques de référence : la Terre possède un seul satellite naturel permanent, la Lune.",
      explanation: isTrue
        ? "Les sources de référence convergent sur le point d'ébullition de l'eau à pression atmosphérique normale."
        : "Les sources astronomiques convergent sur le fait que la Lune est le satellite naturel de la Terre ; l'affirmation de deux lunes est donc fausse.",
      correction: isTrue ? null : "La Terre possède un seul satellite naturel permanent : la Lune.",
      sources,
      contradictions: isTrue ? [] : sources,
      claims: [{ text: claim, verdict: isTrue ? "vrai" : "faux", evidence_score: isTrue ? 96 : 98, explanation: isTrue ? "Affirmation confirmée par les sources de référence." : "Affirmation contredite par les sources de référence." }],
      context: { presentation_mode: true, note: "Scénario de présentation Truth Checker" },
      queries: isTrue ? ["water boiling point 100 C sea level"] : ["Earth natural satellite Moon how many"],
      confidence_breakdown: { source_reliability: isTrue ? 96 : 98, corroboration: 96, consensus: 97 },
      searches_performed: 1,
      elapsed_ms: 1842,
      metadata: { model: "presentation-demo", demo: true, source_count: 3 }
    };
  };

  const getMode = (body) => {
    try {
      const text = typeof body === "string" ? body : JSON.stringify(body || {});
      const parsed = JSON.parse(text);
      const content = String(parsed.content || "").toLowerCase();
      // Two deterministic presentation choices.
      if (/deux lunes|2 lunes|two moons|deux satellite/.test(content)) return { mode: "false", content: parsed.content };
      if (/eau.*100|100.*eau|boit.*100|bout.*100|boiling.*100/.test(content)) return { mode: "true", content: parsed.content };
      // Default presentation scenario: VRAI.
      return { mode: "true", content: parsed.content || undefined };
    } catch {
      return { mode: "true" };
    }
  };

  const sse = (result) => {
    const enc = new TextEncoder();
    const events = [
      ["step", { label: "Lecture du contenu..." }],
      ["search", { query: result.queries[0] }],
      ["step", { label: "Comparaison des sources..." }],
      ["result", result]
    ];
    let i = 0;
    return new ReadableStream({
      async pull(controller) {
        if (i >= events.length) { controller.close(); return; }
        const [event, data] = events[i++];
        await sleep(event === "result" ? 650 : 520);
        controller.enqueue(enc.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      }
    });
  };

  window.fetch = async (input, init = {}) => {
    const url = typeof input === "string" ? input : input?.url || "";
    if (!/\/api\/analyze(?:\/stream)?(?:\?|$)/.test(url)) return realFetch(input, init);

    let body = init.body;
    if (body == null && input instanceof Request) body = await input.clone().text();
    const { mode, content } = getMode(body);
    const result = makeResult(mode, content);

    if (/\/stream(?:\?|$)/.test(url)) {
      return new Response(sse(result), { status: 200, headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" } });
    }

    await sleep(1200);
    return new Response(JSON.stringify(result), { status: 200, headers: { "Content-Type": "application/json" } });
  };
})();
