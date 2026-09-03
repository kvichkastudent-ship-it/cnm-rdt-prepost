// Scoring and aggregation, ported from fetch_rdt_results.py.
//
// This must produce a payload byte-identical to the Python one, otherwise the
// live dashboard and the generated dashboard would disagree about the same
// submissions. gen_js_constants.py supplies the labels and answer key so those
// can never drift; this file mirrors the logic.
//
// Kept free of any Netlify or browser API so it can be exercised directly in a
// browser and diffed against the Python output.

import {
  MAX_SCORE, PASS_THRESHOLD, OPTION_LETTERS, ANSWER_KEY,
  QUESTION_LABELS, OPTION_TEXTS, POSITION_LABELS, TESTTYPE_LABELS,
  PROVINCE_ORDER, PROVINCE_LABELS, PROVINCE_EN, EXPECTED_BY_PROVINCE,
  EXPECTED_BY_PROVINCE_POSITION, NGO_BUCKET_KH, NGO_BUCKET_EN,
} from "./constants.mjs";

// ---------------------------------------------------------------------------
// Python's round() breaks ties to the nearest EVEN digit; JavaScript's
// Math.round() and toFixed() break them upward. That is not academic here: with
// 16 respondents one option share is exactly 6.25%, which Python renders 6.2 and
// naive JavaScript renders 6.3. Every rounded number goes through this.
// ---------------------------------------------------------------------------
export function pyRound(value, digits = 0) {
  if (!isFinite(value)) return value;
  const f = Math.pow(10, digits);
  const scaled = value * f;
  // Work from the decimal text to sidestep binary representation noise, the
  // same thing CPython does before deciding a tie.
  const asText = scaled.toPrecision(15);
  const n = parseFloat(asText);
  const floor = Math.floor(n);
  const frac = n - floor;
  let out;
  if (Math.abs(frac - 0.5) < 1e-9) {
    out = (floor % 2 === 0) ? floor : floor + 1;   // tie -> even
  } else {
    out = Math.round(n);
  }
  return out / f;
}

// Kobo returns bare field names at the top level, or group-prefixed
// ("group_a/q1"). Mirrors get_field() in the Python.
export function getField(submission, field) {
  if (Object.prototype.hasOwnProperty.call(submission, field)) return submission[field];
  for (const key of Object.keys(submission)) {
    if (key.endsWith("/" + field)) return submission[key];
  }
  return null;
}

export function scoreSubmission(sub) {
  const rawType = getField(sub, "test_type");
  const rawPos = getField(sub, "position");
  const rawProv = getField(sub, "province");

  const row = {
    test_type: (rawType in TESTTYPE_LABELS) ? TESTTYPE_LABELS[rawType] : rawType,
    position: (rawPos in POSITION_LABELS) ? POSITION_LABELS[rawPos] : (rawPos || "Unknown"),
    // NGO/partner staff are never asked for a province; give them their own
    // bucket rather than one called "Unknown".
    province: (rawPos === "ngo" && !rawProv) ? NGO_BUCKET_KH
              : (rawProv in PROVINCE_LABELS) ? PROVINCE_LABELS[rawProv] : (rawProv || "Unknown"),
    province_en: (rawPos === "ngo" && !rawProv) ? NGO_BUCKET_EN
                 : (rawProv in PROVINCE_EN) ? PROVINCE_EN[rawProv] : "",
    od: getField(sub, "od"),
    hc: getField(sub, "hc"),
    date: getField(sub, "test_date"),
    position_other: getField(sub, "position_other"),
    org_name: getField(sub, "org_name"),
    province_other: getField(sub, "province_other"),
    od_other: getField(sub, "od_other"),
    hc_other: getField(sub, "hc_other"),
  };

  let total = 0;
  for (const q of Object.keys(ANSWER_KEY)) {
    const { letter, points } = ANSWER_KEY[q];
    const ans = getField(sub, q);
    const isCorrect = ans === letter ? 1 : 0;
    row[q] = isCorrect;
    row[q + "_raw"] = ans;
    row[q + "_pts_earned"] = isCorrect ? points : 0;
    total += row[q + "_pts_earned"];
  }
  row.total_score = total;
  row.total_pct = pyRound((total / MAX_SCORE) * 100, 1);
  return row;
}

export function buildDashboardData(rows, generatedAt) {
  const preRows = rows.filter(r => r.test_type === "pre");
  const postRows = rows.filter(r => r.test_type === "post");

  const avg = vals => vals.length ? pyRound(vals.reduce((a, b) => a + b, 0) / vals.length, 1) : 0;

  const preScores = preRows.map(r => r.total_pct);
  const postScores = postRows.map(r => r.total_pct);
  const avgPre = avg(preScores);
  const avgPost = avg(postScores);
  const avgImprove = pyRound(avgPost - avgPre, 1);

  const passRate = rs => rs.length
    ? pyRound(rs.filter(r => r.total_pct >= PASS_THRESHOLD).length / rs.length * 100, 1)
    : 0;
  const passPre = passRate(preRows);
  const passPost = passRate(postRows);

  // ---- per question -------------------------------------------------------
  const byQuestion = [];
  for (const q of Object.keys(ANSWER_KEY)) {
    const preN = preRows.length, postN = postRows.length;
    const preCorrect = preRows.reduce((a, r) => a + r[q], 0);
    const postCorrect = postRows.reduce((a, r) => a + r[q], 0);

    const options = OPTION_LETTERS.map((letter, i) => {
      const preCount = preRows.filter(r => r[q + "_raw"] === letter).length;
      const postCount = postRows.filter(r => r[q + "_raw"] === letter).length;
      return {
        letter: letter.toUpperCase(),
        text: OPTION_TEXTS[q][i],
        is_correct: letter === ANSWER_KEY[q].letter,
        pre_count: preCount,
        post_count: postCount,
        pre_pct: preN ? pyRound(preCount / preN * 100, 1) : 0,
        post_pct: postN ? pyRound(postCount / postN * 100, 1) : 0,
      };
    });

    const preAcc = preN ? pyRound(preCorrect / preN * 100, 1) : 0;
    const postAcc = postN ? pyRound(postCorrect / postN * 100, 1) : 0;

    byQuestion.push({
      question: QUESTION_LABELS[q],
      question_number: q.toUpperCase(),
      pre_pct: preAcc,
      post_pct: postAcc,
      improvement: pyRound(postAcc - preAcc, 1),
      pre_n: preN,
      post_n: postN,
      pre_correct: preCorrect,
      post_correct: postCorrect,
      correct_letter: ANSWER_KEY[q].letter.toUpperCase(),
      options,
    });
  }

  // ---- by position --------------------------------------------------------
  // Roster order, not alphabetical, and NGO/Partner listed even with nothing
  // received yet - see the matching comment in fetch_rdt_results.py.
  const always = ["PMS", "ODMS", "HC", POSITION_LABELS["ngo"]];
  const seen = new Set(rows.map(r => r.position));
  const positions = always.concat([...seen].filter(p => !always.includes(p)).sort());
  const byPosition = positions.map(pos => {
    const preP = preRows.filter(r => r.position === pos);
    const postP = postRows.filter(r => r.position === pos);
    return {
      position: pos,
      n_pre: preP.length,
      n_post: postP.length,
      pre_pct: avg(preP.map(r => r.total_pct)),
      post_pct: avg(postP.map(r => r.total_pct)),
      pass_pre_pct: passRate(preP),
      pass_post_pct: passRate(postP),
    };
  });

  const passFail = {
    pre: {
      pass: preRows.filter(r => r.total_pct >= PASS_THRESHOLD).length,
      fail: preRows.filter(r => r.total_pct < PASS_THRESHOLD).length,
    },
    post: {
      pass: postRows.filter(r => r.total_pct >= PASS_THRESHOLD).length,
      fail: postRows.filter(r => r.total_pct < PASS_THRESHOLD).length,
    },
  };

  // ---- points and the per-score histogram ---------------------------------
  const pointStats = rs => {
    const pts = rs.map(r => r.total_score);
    return {
      n: rs.length,
      avg_points: pts.length ? pyRound(pts.reduce((a, b) => a + b, 0) / pts.length, 1) : 0,
      avg_pct: avg(rs.map(r => r.total_pct)),
      min_points: pts.length ? Math.min(...pts) : 0,
      max_points: pts.length ? Math.max(...pts) : 0,
    };
  };
  const points = { max_score: MAX_SCORE, pre: pointStats(preRows), post: pointStats(postRows) };

  const scoreHistogram = [];
  for (let s = 0; s <= MAX_SCORE; s++) {
    scoreHistogram.push({
      score: s,
      pre_n: preRows.filter(r => r.total_score === s).length,
      post_n: postRows.filter(r => r.total_score === s).length,
    });
  }

  // ---- by province, in roster order ---------------------------------------
  const expectedByLabel = {};
  for (const [code, n] of Object.entries(EXPECTED_BY_PROVINCE)) {
    if (n !== null && n !== undefined) expectedByLabel[PROVINCE_LABELS[code]] = n;
  }

  const present = new Set(rows.filter(r => r.province).map(r => r.province));
  // Keep provinces with zero submissions in the list - that row is the point.
  const onRoster = new Set(Object.keys(EXPECTED_BY_PROVINCE_POSITION)
    .filter(c => EXPECTED_BY_PROVINCE_POSITION[c])
    .map(c => PROVINCE_LABELS[c]));
  const ordered = PROVINCE_ORDER.map(c => PROVINCE_LABELS[c])
    .filter(l => present.has(l) || onRoster.has(l));
  const extras = [...present]
    .filter(p => !ordered.includes(p) && p !== NGO_BUCKET_KH).sort();
  // NGO/partner staff have no province, so they get their own row at the bottom.
  const provinceOrder = ordered.concat(extras, [NGO_BUCKET_KH]);

  const labelToCode = {};
  for (const c of Object.keys(PROVINCE_LABELS)) labelToCode[PROVINCE_LABELS[c]] = c;

  // PMS / ODMS / HC detail for one province: expected vs received
  const levelsFor = (provLabel, preP, postP) => {
    const cfg = EXPECTED_BY_PROVINCE_POSITION[labelToCode[provLabel]] || {};
    const known = Object.keys(cfg);
    const extra = [...new Set([...preP, ...postP].map(r => r.position))]
      .filter(p => !known.includes(p)).sort();
    const out = [];
    for (const pos of known.concat(extra)) {
      const exp = Object.prototype.hasOwnProperty.call(cfg, pos) ? cfg[pos] : null;
      const nPre = preP.filter(r => r.position === pos).length;
      const nPost = postP.filter(r => r.position === pos).length;
      if (exp === null && !nPre && !nPost) continue;
      out.push({
        position: pos,
        expected: exp,
        n_pre: nPre,
        n_post: nPost,
        missing_pre: exp === null ? null : Math.max(0, exp - nPre),
        missing_post: exp === null ? null : Math.max(0, exp - nPost),
      });
    }
    return out;
  };

  const byProvince = provinceOrder.map(prov => {
    const preP = preRows.filter(r => r.province === prov);
    const postP = postRows.filter(r => r.province === prov);
    const expected = Object.prototype.hasOwnProperty.call(expectedByLabel, prov)
      ? expectedByLabel[prov] : null;
    const first = rows.find(r => r.province === prov);
    return {
      province: prov,
      // by code, not by scanning rows - a province with no submissions still has a name
      province_en: prov === NGO_BUCKET_KH ? NGO_BUCKET_EN
                   : (PROVINCE_EN[labelToCode[prov]] || (first && first.province_en) || ""),
      n_pre: preP.length,
      n_post: postP.length,
      pre_pct: avg(preP.map(r => r.total_pct)),
      post_pct: avg(postP.map(r => r.total_pct)),
      expected,
      missing_pre: expected === null ? null : Math.max(0, expected - preP.length),
      missing_post: expected === null ? null : Math.max(0, expected - postP.length),
      // NGO/partner is one group, not a province with PMS/OD/HC underneath
      levels: prov === NGO_BUCKET_KH ? [] : levelsFor(prov, preP, postP),
    };
  });

  const expTotal = Object.keys(expectedByLabel).length
    ? Object.values(expectedByLabel).reduce((a, b) => a + b, 0) : null;
  let tracking = null;
  if (expTotal) {
    const covered = byProvince.filter(r => r.expected !== null);
    const subPre = covered.reduce((a, r) => a + r.n_pre, 0);
    const subPost = covered.reduce((a, r) => a + r.n_post, 0);
    tracking = {
      expected_total: expTotal,
      provinces_configured: Object.keys(expectedByLabel).length,
      provinces_total: PROVINCE_ORDER.length,   // "other" is a choice, not a province
      pre: { submitted: subPre, missing: Math.max(0, expTotal - subPre),
             rate_pct: pyRound(subPre / expTotal * 100, 1) },
      post: { submitted: subPost, missing: Math.max(0, expTotal - subPost),
              rate_pct: pyRound(subPost / expTotal * 100, 1) },
    };
  }

  return {
    generated_at: generatedAt,
    kpis: {
      n_pre: preRows.length,
      n_post: postRows.length,
      avg_pre_pct: avgPre,
      avg_post_pct: avgPost,
      avg_improvement_pct: avgImprove,
      pass_pre_pct: passPre,
      pass_post_pct: passPost,
    },
    by_question: byQuestion,
    by_position: byPosition,
    pass_fail: passFail,
    pass_threshold: PASS_THRESHOLD,
    tracking,
    points,
    score_histogram: scoreHistogram,
    by_province: byProvince,
  };
}
