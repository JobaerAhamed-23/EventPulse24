/**
 * The city page's **404 document**, read out of the served HTML.
 *
 * **Next's not-found boundary is rendered through the RSC payload**, so the copy may
 * appear in the flight data rather than as literal markup in the body. This probe
 * reports *both* — what the body contains and what the flight data contains — because
 * "the copy is in the response" and "the copy is in the document" are different claims.
 */
const BASE = process.env.PAGE_BASE ?? "http://127.0.0.1:3220";

const response = await fetch(`${BASE}/events-in-atlantis`, { redirect: "manual" });
const html = await response.text();

const bodyOnly = html.split("</body>")[0] ?? html;

console.log(`status                          ${response.status}`);
console.log(`content-type                    ${response.headers.get("content-type")}`);
console.log(
  `x-nextjs-cache                  ${response.headers.get("x-nextjs-cache") ?? "(none)"}`,
);
console.log(`body has an <h1>                ${/<h1[\s>]/i.test(bodyOnly)}`);
console.log(`body has the 404 copy           ${bodyOnly.includes("We don't have that city.")}`);
console.log(`flight has the 404 copy         ${html.includes("We don't have that city.")}`);
console.log(`flight has an <h1>              ${/"h1"/.test(html)}`);
console.log(`body length                     ${bodyOnly.length}`);
