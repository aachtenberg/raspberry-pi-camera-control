// Syntax-check the inline <script> blocks of HTML templates. No browser needed.
// Usage: node tests/check_template_js.js templates/*.html
const fs = require('fs');

let failed = false;
for (const file of process.argv.slice(2)) {
    const html = fs.readFileSync(file, 'utf8');
    const blocks = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)];
    blocks.forEach((block, index) => {
        try {
            new Function(block[1]);
        } catch (error) {
            failed = true;
            console.error(`${file}: inline script ${index + 1}: ${error.message}`);
        }
    });
    console.log(`${file}: ${blocks.length} inline script(s) checked`);
}
process.exit(failed ? 1 : 0);
