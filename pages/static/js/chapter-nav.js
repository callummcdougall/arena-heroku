/**
 * Chapter Navigation - Client-side navigation (vanilla JS)
 */

(function() {
    'use strict';

    // Cache for loaded sections
    const sectionCache = new Map();

    // Current state
    let currentChapterId = null;
    let currentSectionId = null;
    let currentSubsectionId = null;
    let chapter = null;

    // DOM elements (set during init)
    let contentArea = null;
    let sectionList = null;
    let subsectionContainer = null;
    let subsectionList = null;
    let tocContainer = null;
    let tocList = null;
    let sidebar = null;
    let sidebarToggle = null;
    let resizeHandle = null;

    /**
     * Initialize the navigation system
     */
    function init() {
        // Get DOM elements
        contentArea = document.getElementById('content-area');
        sectionList = document.getElementById('section-list');
        subsectionContainer = document.querySelector('.sidebar-subsections');
        subsectionList = document.getElementById('subsection-list');
        tocContainer = document.getElementById('sidebar-toc');
        tocList = document.getElementById('toc-list');

        if (!contentArea) {
            console.warn('Chapter navigation: content-area not found');
            return;
        }

        // Get initial state from data attributes
        const chapterDataEl = document.getElementById('chapter-data');
        if (chapterDataEl) {
            try {
                chapter = JSON.parse(chapterDataEl.textContent);
                currentChapterId = chapter.id;
            } catch (e) {
                console.error('Failed to parse chapter data:', e);
                return;
            }
        }

        // Get current section/subsection from URL
        const path = window.location.pathname;
        const parts = path.split('/').filter(p => p);
        if (parts.length >= 2) {
            currentSectionId = parts[1];
        }
        if (parts.length >= 3) {
            currentSubsectionId = parts[2];
        }

        // Load initial subsections data if available
        const subsectionsDataEl = document.getElementById('subsections-data');
        if (subsectionsDataEl && currentSectionId) {
            try {
                const subsections = JSON.parse(subsectionsDataEl.textContent);
                sectionCache.set(currentSectionId, {
                    section: getCurrentSectionMeta(),
                    subsections: subsections,
                });
            } catch (e) {
                console.error('Failed to parse subsections data:', e);
            }
        }

        // Set up event listeners
        setupEventListeners();

        // Update UI to reflect current state
        updateActiveStates();

        // Initialize sidebar functionality
        initSidebar();

        // Start background preloading after a short delay
        setTimeout(preloadOtherSections, 1000);

        // Handle browser back/forward
        window.addEventListener('popstate', handlePopState);
    }

    /**
     * Initialize sidebar resize and collapse functionality
     */
    function initSidebar() {
        sidebar = document.getElementById('chapter-sidebar');
        sidebarToggle = document.getElementById('sidebar-toggle');
        resizeHandle = document.getElementById('sidebar-resize-handle');

        if (!sidebar) return;

        // Load saved sidebar width from localStorage
        const savedWidth = localStorage.getItem('sidebarWidth');
        if (savedWidth) {
            sidebar.style.width = savedWidth + 'px';
            updateTogglePosition(parseInt(savedWidth));
        }

        // Load collapsed state
        const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
        if (isCollapsed) {
            sidebar.classList.add('collapsed');
            if (sidebarToggle) sidebarToggle.classList.add('collapsed');
        }

        // Toggle button click
        if (sidebarToggle) {
            sidebarToggle.addEventListener('click', toggleSidebar);
        }

        // Resize handle drag
        if (resizeHandle) {
            setupResizeHandle();
        }
    }

    /**
     * Toggle sidebar collapsed state
     */
    function toggleSidebar() {
        if (!sidebar || !sidebarToggle) return;

        const isCollapsed = sidebar.classList.toggle('collapsed');
        sidebarToggle.classList.toggle('collapsed', isCollapsed);

        localStorage.setItem('sidebarCollapsed', isCollapsed);

        if (!isCollapsed) {
            // Restore width when expanding
            const savedWidth = localStorage.getItem('sidebarWidth');
            if (savedWidth) {
                updateTogglePosition(parseInt(savedWidth));
            } else {
                updateTogglePosition(280); // Default width
            }
        }
    }

    /**
     * Set up resize handle drag functionality
     */
    function setupResizeHandle() {
        let isResizing = false;
        let startX = 0;
        let startWidth = 0;

        resizeHandle.addEventListener('mousedown', function(e) {
            isResizing = true;
            startX = e.clientX;
            startWidth = sidebar.offsetWidth;
            sidebar.classList.add('resizing');
            resizeHandle.classList.add('active');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
        });

        document.addEventListener('mousemove', function(e) {
            if (!isResizing) return;

            const diff = e.clientX - startX;
            let newWidth = startWidth + diff;

            // Clamp to min/max
            newWidth = Math.max(200, Math.min(450, newWidth));

            sidebar.style.width = newWidth + 'px';
            updateTogglePosition(newWidth);
        });

        document.addEventListener('mouseup', function() {
            if (!isResizing) return;

            isResizing = false;
            sidebar.classList.remove('resizing');
            resizeHandle.classList.remove('active');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';

            // Save width to localStorage
            const width = sidebar.offsetWidth;
            localStorage.setItem('sidebarWidth', width);
        });
    }

    /**
     * Update toggle button position based on sidebar width
     */
    function updateTogglePosition(width) {
        if (sidebarToggle && !sidebar.classList.contains('collapsed')) {
            sidebarToggle.style.left = width + 'px';
        }
    }

    /**
     * Get current section metadata from chapter
     */
    function getCurrentSectionMeta() {
        if (!chapter || !currentSectionId) return null;
        return chapter.sections.find(s => s.id === currentSectionId);
    }

    /**
     * Set up click handlers for navigation links
     */
    function setupEventListeners() {
        // Section links in sidebar
        if (sectionList) {
            sectionList.addEventListener('click', function(event) {
                const link = event.target.closest('.section-link');
                if (!link) return;

                event.preventDefault();
                const sectionId = link.dataset.sectionId;
                if (sectionId && sectionId !== currentSectionId) {
                    navigateToSection(sectionId);
                }
            });
        }

        // Subsection links
        if (subsectionContainer) {
            subsectionContainer.addEventListener('click', function(event) {
                const link = event.target.closest('.subsection-link');
                if (!link) return;

                event.preventDefault();
                const subsectionId = link.dataset.subsectionId;
                if (subsectionId) {
                    navigateToSubsection(subsectionId);
                }
            });
        }

        // TOC links - scroll to anchor
        if (tocContainer) {
            tocContainer.addEventListener('click', function(event) {
                const link = event.target.closest('.toc-link');
                if (!link) return;

                event.preventDefault();
                const href = link.getAttribute('href');
                const targetId = href ? href.slice(1) : null;
                if (targetId) {
                    const target = document.getElementById(targetId);
                    if (target) {
                        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        history.replaceState(null, '', `#${targetId}`);
                    }
                }
            });
        }

        // Handle clicks on section cards in chapter overview
        if (contentArea) {
            contentArea.addEventListener('click', function(event) {
                const card = event.target.closest('[data-section-link]');
                if (!card) return;

                event.preventDefault();
                const sectionId = card.dataset.sectionId;
                if (sectionId) {
                    navigateToSection(sectionId);
                }
            });
        }
    }

    /**
     * Navigate to a different section
     */
    async function navigateToSection(sectionId) {
        if (sectionId === currentSectionId) return;

        // Show loading state
        showLoading();

        try {
            // Get section data (from cache or fetch)
            const data = await getSectionData(sectionId);

            // Update current state
            currentSectionId = sectionId;
            currentSubsectionId = data.subsections[0]?.id || null;

            // Update URL
            const newUrl = `/${currentChapterId}/${currentSectionId}/${currentSubsectionId || ''}`;
            history.pushState({ chapterId: currentChapterId, sectionId, subsectionId: currentSubsectionId }, '', newUrl);

            // Render content
            renderSection(data);
            updateActiveStates();

            // Update right sidebar context selection
            if (window.rightSidebarSelectSection) {
                window.rightSidebarSelectSection(sectionId);
            }

        } catch (error) {
            console.error('Failed to load section:', error);
            showError('Failed to load section. Please try again.');
        }
    }

    /**
     * Navigate to a different subsection within current section
     */
    function navigateToSubsection(subsectionId) {
        if (!currentSectionId) return;

        const data = sectionCache.get(currentSectionId);
        if (!data) return;

        const subsection = data.subsections.find(s => s.id === subsectionId);
        if (!subsection) return;

        currentSubsectionId = subsectionId;

        // Update URL
        const newUrl = `/${currentChapterId}/${currentSectionId}/${subsectionId}/`;
        history.pushState({ chapterId: currentChapterId, sectionId: currentSectionId, subsectionId }, '', newUrl);

        // Render subsection content
        renderSubsection(subsection);
        updateActiveStates();

        // Scroll to top
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    /**
     * Get section data from cache or fetch from API
     */
    async function getSectionData(sectionId) {
        // Check cache first
        if (sectionCache.has(sectionId)) {
            return sectionCache.get(sectionId);
        }

        // Fetch from API
        const response = await fetch(`/api/${currentChapterId}/${sectionId}/`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        // Cache the result
        sectionCache.set(sectionId, data);

        return data;
    }

    /**
     * Preload other sections in the background
     */
    async function preloadOtherSections() {
        if (!chapter || !chapter.sections) return;

        for (const section of chapter.sections) {
            if (section.id === currentSectionId) continue;
            if (sectionCache.has(section.id)) continue;

            try {
                await new Promise(resolve => setTimeout(resolve, 500));
                await getSectionData(section.id);
            } catch (e) {
                console.debug('Preload failed for:', section.id);
            }
        }
    }

    /**
     * Render a section
     */
    function renderSection(data) {
        // Update subsection list
        renderSubsectionList(data.subsections);

        // Show first subsection content
        if (data.subsections.length > 0) {
            const subsection = data.subsections.find(s => s.id === currentSubsectionId) || data.subsections[0];
            currentSubsectionId = subsection.id;
            renderSubsection(subsection);
        } else {
            contentArea.innerHTML = '<p>No content available.</p>';
        }
    }

    /**
     * Render the subsection list
     */
    function renderSubsectionList(subsections) {
        if (!subsectionList) return;

        // Hide if only one or no subsections
        if (!subsections || subsections.length <= 1) {
            if (subsectionContainer) subsectionContainer.style.display = 'none';
            subsectionList.innerHTML = '';
            return;
        }

        if (subsectionContainer) subsectionContainer.style.display = 'block';

        // Build HTML for subsection list
        subsectionList.innerHTML = subsections.map(sub => `
            <li>
                <a href="/${currentChapterId}/${currentSectionId}/${sub.id}/"
                   class="subsection-link ${sub.id === currentSubsectionId ? 'active' : ''}"
                   data-subsection-id="${sub.id}">
                    <span class="subsection-title">${sub.title}</span>
                </a>
            </li>
        `).join('');
    }

    /**
     * Render a subsection's content
     */
    function renderSubsection(subsection) {
        if (!contentArea) return;

        // Fade out, update, fade in
        contentArea.style.opacity = '0';
        contentArea.style.transition = 'opacity 100ms';

        setTimeout(() => {
            contentArea.innerHTML = `<article class="markdown-content">${subsection.html}</article>`;

            // Re-render LaTeX after content is loaded
            if (window.renderMath) {
                window.renderMath(contentArea);
            }

            contentArea.style.opacity = '1';
            contentArea.style.transition = 'opacity 150ms';
        }, 100);

        // Update TOC
        renderToc(subsection.headers);
    }

    /**
     * Render table of contents
     */
    function renderToc(headers) {
        if (!tocList) return;

        // Hide if no headers
        if (!headers || headers.length === 0) {
            if (tocContainer) tocContainer.style.display = 'none';
            tocList.innerHTML = '';
            return;
        }

        if (tocContainer) tocContainer.style.display = 'block';

        // Build HTML for TOC
        tocList.innerHTML = headers.map(h => `
            <li class="toc-item toc-level-${h.level}">
                <a href="#${h.id}" class="toc-link">${h.title}</a>
            </li>
        `).join('');
    }

    /**
     * Update active states in navigation
     */
    function updateActiveStates() {
        // Update section list
        if (sectionList) {
            sectionList.querySelectorAll('.section-link').forEach(link => {
                link.classList.toggle('active', link.dataset.sectionId === currentSectionId);
            });
        }

        // Update subsection list
        if (subsectionList) {
            subsectionList.querySelectorAll('.subsection-link').forEach(link => {
                link.classList.toggle('active', link.dataset.subsectionId === currentSubsectionId);
            });
        }
    }

    /**
     * Handle browser back/forward navigation
     */
    async function handlePopState(e) {
        const state = e.state;
        if (!state) {
            // No state, parse from URL
            const path = window.location.pathname;
            const parts = path.split('/').filter(p => p);
            if (parts.length >= 2 && parts[0] === currentChapterId) {
                const sectionId = parts[1];
                const subsectionId = parts[2] || null;

                if (sectionId !== currentSectionId) {
                    currentSectionId = sectionId;
                    currentSubsectionId = subsectionId;
                    const data = await getSectionData(sectionId);
                    renderSection(data);
                } else if (subsectionId !== currentSubsectionId) {
                    currentSubsectionId = subsectionId;
                    const data = sectionCache.get(currentSectionId);
                    if (data) {
                        const subsection = data.subsections.find(s => s.id === subsectionId);
                        if (subsection) {
                            renderSubsection(subsection);
                        }
                    }
                }
                updateActiveStates();
            }
            return;
        }

        // Use state from history
        if (state.chapterId !== currentChapterId) {
            window.location.reload();
            return;
        }

        if (state.sectionId !== currentSectionId) {
            currentSectionId = state.sectionId;
            currentSubsectionId = state.subsectionId;
            const data = await getSectionData(state.sectionId);
            renderSection(data);
        } else if (state.subsectionId !== currentSubsectionId) {
            currentSubsectionId = state.subsectionId;
            const data = sectionCache.get(currentSectionId);
            if (data) {
                const subsection = data.subsections.find(s => s.id === state.subsectionId);
                if (subsection) {
                    renderSubsection(subsection);
                }
            }
        }
        updateActiveStates();
    }

    /**
     * Show loading indicator
     */
    function showLoading() {
        if (!contentArea) return;
        contentArea.innerHTML = `
            <div class="loading-indicator">
                <div class="loading-spinner"></div>
                <p>Loading...</p>
            </div>
        `;
    }

    /**
     * Show error message
     */
    function showError(message) {
        if (!contentArea) return;
        contentArea.innerHTML = `
            <div class="error-message">
                <p>${message}</p>
            </div>
        `;
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
