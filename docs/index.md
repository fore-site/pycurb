---
hide:
  - navigation
  - toc
---

# PyCurb

## Framework-agnostic rate limiting for Python

PyCurb is a rate-limiting library that works with FastAPI, Flask, Django, and general Python applications. Choose from five algorithms, pluggable storage backends, and framework adapters — all via a simple, consistent API.

<div class="grid" style="display: flex; gap: 12px; margin: 24px 0; flex-wrap: wrap;">
    <a href="getting_started/" class="md-button md-button--primary" style="font-size: 1.1rem; padding: 12px 28px;">
        Get Started
    </a>
    <a href="https://github.com/fore-site/pycurb" class="md-button" style="font-size: 1.1rem; padding: 12px 28px;">
        GitHub
    </a>
</div>

<script>
// Insert a header-level theme icon toggle and sync with the theme radios.
document.addEventListener('DOMContentLoaded', function(){
    try{
        var headerInner = document.querySelector('.md-header__inner');
        if(!headerInner) return;

        // SVG icons (sun / moon) — match Material header style
        var sunSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M6.76 4.84l-1.8-1.79L3.17 4.84l1.79 1.8L6.76 4.84zM1 13h3v-2H1v2zm10 9h2v-3h-2v3zm7.24-2.76l1.79 1.8 1.79-1.79-1.8-1.8-1.78 1.79zM17 11V9h-2v2h2zm-5-7h-2v3h2V4zm4.24 2.76l1.78-1.79L17.24 3l-1.79 1.79L16.24 6.76zM12 8a4 4 0 100 8 4 4 0 000-8z"/></svg>';
        var moonSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 3a9 9 0 000 18 9 9 0 006.32-15.32A7 7 0 0112 3z"/></svg>';

        // Create icon button
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'md-header__button md-icon';
        btn.setAttribute('aria-label', 'Toggle theme');
        btn.style.marginLeft = '8px';

        // Insert into header after the title
        var title = headerInner.querySelector('.md-header__title');
        if(title && title.parentNode) title.parentNode.insertBefore(btn, title.nextSibling);
        else headerInner.appendChild(btn);

        function setScheme(scheme){
            document.body.setAttribute('data-md-color-scheme', scheme);
            try{ __md_set('__palette', { color: { media: '(prefers-color-scheme)', scheme: scheme, primary: 'indigo', accent: 'indigo' } }); }catch(e){}
            // Update radio inputs
            var radios = document.querySelectorAll('input[id^="__palette_"]');
            radios.forEach(function(r){
                var s = r.getAttribute('data-md-color-scheme');
                if(s === scheme) r.checked = true; else r.checked = false;
            });
            // Update icon
            btn.innerHTML = (scheme === 'slate') ? moonSvg : sunSvg;
        }

        // Initialize icon to current scheme
        var initial = document.body.getAttribute('data-md-color-scheme') || 'default';
        btn.innerHTML = (initial === 'slate') ? moonSvg : sunSvg;

        btn.addEventListener('click', function(){
            var current = document.body.getAttribute('data-md-color-scheme') || 'default';
            var next = current === 'default' ? 'slate' : 'default';
            setScheme(next);
        });

        // Sync radios on load
        var radios = document.querySelectorAll('input[id^="__palette_"]');
        radios.forEach(function(r){
            r.addEventListener('change', function(){
                var s = r.getAttribute('data-md-color-scheme');
                if(r.checked && s) setScheme(s);
            });
        });

    }catch(e){console.warn(e)}
});
</script>

## Why PyCurb?

<div class="grid cards" markdown>

- **Five algorithms:** Sliding Window, Fixed Window, Token Bucket, Leaky Bucket, and GCRA — choose the right strategy for your workload.
- **Async & sync:** Works with ASGI (FastAPI) and WSGI (Flask, Django) environments.
- **Pluggable storage:** In-memory and Redis backends with graceful fallback and connection pooling.
- **Framework adapters:** Ready-to-use adapters for FastAPI, Flask, and Django — minimal integration code.
- **Composite limits:** Enforce multiple rules simultaneously (for example, per-minute + per-hour) with a single check.
- **High performance:** Minimal overhead and optimized for production workloads.

</div>

---

## Installation

=== "Core"

    ```bash
    pip install pycurb
    ```

=== "With Redis"

    ```bash
    pip install "pycurb[redis]"
    ```

=== "With FastAPI"

    ```bash
    pip install "pycurb[fastapi]"
    ```

=== "With Django"

    ```bash
    pip install "pycurb[django]"
    ```

=== "With Flask"

    ```bash
    pip install "pycurb[flask]"
    ```

=== "All"

    ```bash
    pip install "pycurb[all]"
    ```

---

## What Next?

<div class="grid" style="display: flex; gap: 16px; margin: 16px 0; flex-wrap: wrap;"> 
    <div style="flex: 1; min-width: 200px; background: var(--md-code-bg-color); padding: 20px; border-radius: 8px;"> 
        <strong>Getting Started</strong>
        <p style="margin: 8px 0 12px 0;">Install PyCurb and write a rate-limited endpoint in minutes.</p>
        <a href="getting_started/" style="font-weight: 600;">Learn More →</a>
    </div>
    <div style="flex: 1; min-width: 200px; background: var(--md-code-bg-color); padding: 20px; border-radius: 8px;"> 
        <strong>Algorithms</strong>
        <p style="margin: 8px 0 12px 0;">Learn about the five rate-limiting strategies and recommended use cases.</p>
        <a href="algorithms/" style="font-weight: 600;">Learn More →</a>
    </div>
    <div style="flex: 1; min-width: 200px; background: var(--md-code-bg-color); padding: 20px;  border-radius: 8px;"> 
        <strong>Framework adapters</strong>
        <p style="margin: 8px 0 12px 0;">Quick integrations for FastAPI, Flask, and Django.</p>
        <a href="getting_started/#framework-adapters" style="font-weight: 600;">Learn More →</a>
    </div>
</div>

## Production‑Ready

<div class="grid cards" markdown>

- **Type-safe:** Fully annotated with type hints for better IDE support.
- **Tested:** Comprehensive test suite with broad coverage.
- **Benchmarked:** Performance-tested across algorithms and storage backends.
- **Documented:** Extensive documentation with practical examples.

</div>

## License

PyCurb is released under the Apache License 2.0.

<div style="text-align: center; margin-top: 40px; padding: 20px 0; border-top: 1px solid var(--md-default-fg-color--lightest);"> 
    <p style="font-size: 0.9rem; color: var(--md-default-fg-color--lighter);"> Built by the PyCurb team &nbsp;·&nbsp; <a href="https://github.com/fore-site/pycurb" style="color: var(--md-default-fg-color--light);">GitHub</a> &nbsp;·&nbsp; <a href="changelog/" style="color: var(--md-default-fg-color--light);">Changelog</a> </p> 
</div>
