/* ============================================================
   ReelMind - app.js
   All interactive behaviors: navbar scroll, chat demo animation,
   FAQ accordion, copy buttons, scroll reveal, mobile nav.
============================================================ */

'use strict';

/* ============================================================
   1. NAVBAR – Scrolled state
============================================================ */
(function initNavbar() {
  const navbar = document.getElementById('navbar');
  const hamburger = document.getElementById('hamburger');
  const mobileNav = document.getElementById('mobile-nav');

  window.addEventListener('scroll', () => {
    if (window.scrollY > 40) {
      navbar.classList.add('scrolled');
    } else {
      navbar.classList.remove('scrolled');
    }
  }, { passive: true });

  hamburger.addEventListener('click', () => {
    mobileNav.classList.toggle('open');
  });

  // Close mobile nav when a link is clicked
  mobileNav.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => mobileNav.classList.remove('open'));
  });
})();


/* ============================================================
   2. CHAT DEMO – Animated conversation loop
============================================================ */
(function initChatDemo() {
  const body = document.getElementById('chat-demo-body');
  const inputField = document.getElementById('chat-demo-input-field');

  const conversations = [
    {
      user: "Find the reel about sustainable cooking tips",
      ai: "Found it! A reel by @greenplate from March 2024 covers low-waste meal prep, seasonal ingredient sourcing, and zero-plastic kitchen swaps. Very practical content.",
      source: "📹 2024-03-08_greenplate.mp4"
    },
    {
      user: "What was that guitar tutorial reel?",
      ai: "That's from @musiclab_daily — recorded in October 2023. It covers fingerpicking patterns for beginners, specifically the Travis picking technique, with tab overlays on screen.",
      source: "📹 2023-10-22_musiclab_daily.mp4"
    },
    {
      user: "Show me reels about productivity and deep work",
      ai: "Found 3 matching reels! The most relevant is by @focusflow from January 2024 — it mentions the Pomodoro technique, phone-free blocks, and building a distraction-free environment.",
      source: "📹 3 reels matched · Top: 2024-01-15_focusflow.mp4"
    },
    {
      user: "Any reels mentioning Tokyo travel tips?",
      ai: "Yes! A travel vlog by @tokyo_wanderer from May 2024 covers IC card usage, the best ramen spots in Shinjuku, and navigating the JR pass.",
      source: "📹 2024-05-30_tokyo_wanderer.mp4"
    }
  ];

  let convIndex = 0;
  let animating = false;

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function createTypingBubble() {
    const msg = document.createElement('div');
    msg.className = 'chat-msg chat-msg--ai';
    msg.innerHTML = `
      <div class="chat-avatar chat-avatar--ai">🤖</div>
      <div class="chat-bubble">
        <div class="chat-typing">
          <span></span><span></span><span></span>
        </div>
      </div>`;
    return msg;
  }

  function createUserBubble(text) {
    const msg = document.createElement('div');
    msg.className = 'chat-msg chat-msg--user';
    msg.innerHTML = `
      <div class="chat-avatar chat-avatar--user">👤</div>
      <div class="chat-bubble">${text}</div>`;
    return msg;
  }

  function createAiBubble(text, source) {
    const msg = document.createElement('div');
    msg.className = 'chat-msg chat-msg--ai';
    msg.innerHTML = `
      <div class="chat-avatar chat-avatar--ai">🤖</div>
      <div class="chat-bubble">
        ${text}
        <div class="chat-source-tag">${source}</div>
      </div>`;
    return msg;
  }

  async function typeIntoInput(text) {
    inputField.value = '';
    for (let i = 0; i <= text.length; i++) {
      inputField.value = text.slice(0, i);
      await sleep(35 + Math.random() * 30);
    }
  }

  async function runConversation() {
    if (animating) return;
    animating = true;

    const conv = conversations[convIndex % conversations.length];
    convIndex++;

    // Clear old messages if more than 4
    while (body.children.length >= 4) {
      body.removeChild(body.firstChild);
    }

    // Type user message into input
    await typeIntoInput(conv.user);
    await sleep(400);

    // Add user message to chat
    inputField.value = '';
    const userMsg = createUserBubble(conv.user);
    body.appendChild(userMsg);
    body.scrollTop = body.scrollHeight;
    await sleep(600);

    // Show typing indicator
    const typing = createTypingBubble();
    body.appendChild(typing);
    body.scrollTop = body.scrollHeight;

    // Simulate AI thinking time (1.5 – 2.5 seconds)
    await sleep(1500 + Math.random() * 1000);

    // Replace typing with actual response
    body.removeChild(typing);
    const aiMsg = createAiBubble(conv.ai, conv.source);
    body.appendChild(aiMsg);
    body.scrollTop = body.scrollHeight;

    await sleep(4000);
    animating = false;
  }

  // Kick off the loop
  async function loop() {
    await sleep(1200);
    while (true) {
      await runConversation();
      await sleep(1000);
    }
  }

  loop();
})();


/* ============================================================
   3. FAQ ACCORDION
============================================================ */
function toggleFaq(id) {
  const item = document.getElementById(id);
  if (!item) return;
  const isOpen = item.classList.contains('open');

  // Close all
  document.querySelectorAll('.faq-item').forEach(el => el.classList.remove('open'));

  // Open clicked (if wasn't open)
  if (!isOpen) item.classList.add('open');
}

// Expose globally for inline onclick handlers
window.toggleFaq = toggleFaq;


/* ============================================================
   4. COPY CODE BUTTON
============================================================ */
function copyCode(preId, btnId) {
  const pre = document.getElementById(preId);
  const btn = document.getElementById(btnId);
  if (!pre || !btn) return;

  const text = pre.textContent;
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = 'Copy';
      btn.classList.remove('copied');
    }, 2000);
  }).catch(() => {
    // Fallback for older browsers
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 2000);
  });
}

window.copyCode = copyCode;


/* ============================================================
   5. SCROLL REVEAL – Intersection Observer
============================================================ */
(function initReveal() {
  // Add reveal class to all sections and major cards
  const selectors = [
    '.feature-card',
    '.hiw-step',
    '.tech-card',
    '.setup-step',
    '.faq-item',
    '.requirements-card',
    '.hero-stats',
    '.chat-demo'
  ];

  const elements = document.querySelectorAll(selectors.join(', '));
  elements.forEach((el, i) => {
    el.classList.add('reveal');
    // Stagger delay based on siblings
    el.style.transitionDelay = `${(i % 4) * 80}ms`;
  });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -60px 0px' });

  elements.forEach(el => observer.observe(el));
})();


/* ============================================================
   6. SMOOTH SCROLL – Offset for fixed navbar
============================================================ */
(function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      const target = document.querySelector(this.getAttribute('href'));
      if (!target) return;
      e.preventDefault();
      const offset = 80; // navbar height
      const top = target.getBoundingClientRect().top + window.pageYOffset - offset;
      window.scrollTo({ top, behavior: 'smooth' });
    });
  });
})();


/* ============================================================
   7. VECTOR BAR CHART – Animate on scroll into view
============================================================ */
(function initVectorBars() {
  const chart = document.getElementById('vector-bar-chart');
  if (!chart) return;

  const bars = chart.querySelectorAll('.vbar');

  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        bars.forEach((bar, i) => {
          bar.style.animationDelay = `${i * 80}ms`;
          bar.style.animationFillMode = 'both';
        });
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.3 });

  observer.observe(chart);
})();


/* ============================================================
   8. ACTIVE NAV LINK – Highlight based on scroll position
============================================================ */
(function initActiveNav() {
  const sections = ['features', 'how-it-works', 'tech-stack', 'setup'];
  const navLinks = {
    'features':     document.getElementById('nav-features'),
    'how-it-works': document.getElementById('nav-how'),
    'tech-stack':   document.getElementById('nav-tech'),
    'setup':        document.getElementById('nav-setup'),
  };

  function updateActive() {
    let current = '';
    sections.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      if (window.scrollY >= el.offsetTop - 120) {
        current = id;
      }
    });

    Object.entries(navLinks).forEach(([id, link]) => {
      if (!link) return;
      if (id === current) {
        link.style.color = 'var(--text-primary)';
        link.style.background = 'rgba(255,255,255,0.07)';
      } else {
        link.style.color = '';
        link.style.background = '';
      }
    });
  }

  window.addEventListener('scroll', updateActive, { passive: true });
})();
