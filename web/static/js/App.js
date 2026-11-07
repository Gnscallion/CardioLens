/* 根组件：HR Dashboard 风格的侧边导航、顶栏与内容区。 */
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { NAV_ITEMS } from './router.js';
import { store } from './store.js';

export default {
  name: 'App',
  setup() {
    const route = useRoute();
    const router = useRouter();
    const activeNav = computed(() => route.meta?.nav || '');
    const searchText = ref('');
    const searchFocused = ref(false);
    const searchLoading = ref(false);
    const searchHighlighted = ref(-1);
    const profileOpen = ref(false);
    const user = ref(null);
    const notifications = ref([]);
    const unreadNotifications = ref(0);
    const notificationsOpen = ref(false);

    const searchActions = [
      { key: 'home', label: '首页', hint: '返回工作台', to: '/', keywords: '首页 工作台 home' },
      { key: 'analyze', label: 'ECG 分析', hint: '开始新的心电分析', to: '/analyze', keywords: '分析 ecg 心电 analyze' },
      { key: 'history', label: '分析历史', hint: '查看已保存的分析报告', to: '/history', keywords: '历史 记录 报告 history' },
      { key: 'research', label: '科研实验', hint: '查看科研实验工具', to: '/research', keywords: '科研 实验 research' },
      { key: 'about', label: '关于', hint: '查看系统说明', to: '/about', keywords: '关于 说明 about' },
    ];
    const searchQuery = computed(() => searchText.value.trim().toLowerCase());
    const searchActionResults = computed(() => searchActions.filter((item) => {
      if (!searchQuery.value) return true;
      return `${item.label} ${item.hint} ${item.keywords}`.toLowerCase().includes(searchQuery.value);
    }));
    const searchHistoryResults = computed(() => (store.history || []).filter((item) => {
      if (!searchQuery.value) return true;
      return `${item.title || ''} ${item.record_id || ''}`.toLowerCase().includes(searchQuery.value);
    }).slice(0, 6));
    const searchResults = computed(() => [
      ...searchActionResults.value.map((item) => ({ type: 'action', item })),
      ...searchHistoryResults.value.map((item) => ({ type: 'history', item })),
    ]);

    async function loadUser() {
      try {
        const response = await fetch('/api/auth/me');
        const data = await response.json();
        user.value = data.user || null;
      }
      catch { user.value = null; }
    }
    async function loadNotifications() {
      try { const r = await fetch('/api/notifications'); const d = await r.json(); notifications.value = d.items || []; unreadNotifications.value = d.unread || 0; }
      catch { notifications.value = []; }
    }
    async function activateSearch() {
      searchFocused.value = true;
      searchHighlighted.value = -1;
      if (store.historyLoaded || searchLoading.value) return;
      searchLoading.value = true;
      try { await store.loadHistory(); }
      catch (err) { store.notify(`历史记录加载失败：${err.message}`, 'err'); }
      finally { searchLoading.value = false; }
    }
    function closeSearchSoon() {
      window.setTimeout(() => { searchFocused.value = false; }, 120);
    }
    function selectSearchResult(result) {
      const target = result.type === 'history' ? `/history/${result.item.id}` : result.item.to;
      searchText.value = '';
      searchFocused.value = false;
      router.push(target);
    }
    function moveSearch(delta) {
      if (!searchFocused.value) searchFocused.value = true;
      const count = searchResults.value.length;
      if (!count) return;
      searchHighlighted.value = (searchHighlighted.value + delta + count) % count;
    }
    function handleSearchKeydown(event) {
      if (event.key === 'ArrowDown') { event.preventDefault(); moveSearch(1); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); moveSearch(-1); }
      else if (event.key === 'Escape') { event.preventDefault(); searchFocused.value = false; }
    }
    function clearSearch() { searchText.value = ''; searchHighlighted.value = -1; }
    function submitSearch() {
      if (!searchQuery.value) {
        searchFocused.value = true;
        return;
      }
      const selected = (searchHighlighted.value >= 0 ? searchResults.value[searchHighlighted.value] : null) || searchResults.value[0];
      if (selected) return selectSearchResult(selected);
      store.notify(`没有找到“${searchText.value.trim()}”对应的功能或分析记录`, 'info');
    }
    function openActivity() { router.push('/research'); }
    async function openMessages() { notificationsOpen.value = !notificationsOpen.value; if (notificationsOpen.value) await loadNotifications(); }
    async function markNotification(item) { if (!item.is_read) { await fetch(`/api/notifications/${item.id}/read`, { method: 'POST' }); item.is_read = 1; unreadNotifications.value = Math.max(0, unreadNotifications.value - 1); } }
    async function markAllNotifications() { await fetch('/api/notifications/read-all', { method: 'POST' }); notifications.value.forEach((n) => { n.is_read = 1; }); unreadNotifications.value = 0; }
    async function logout() {
      await fetch('/api/auth/logout', { method: 'POST' });
      user.value = null;
      profileOpen.value = false;
      store.notify('已退出登录', 'ok');
      router.push('/');
    }
    onMounted(() => { loadUser(); loadNotifications(); });

    return {
      store, NAV_ITEMS, activeNav, searchText, searchFocused, searchLoading,
      searchActionResults, searchHistoryResults, searchHighlighted, profileOpen, user, notifications, unreadNotifications, notificationsOpen,
      activateSearch, closeSearchSoon, selectSearchResult, submitSearch, handleSearchKeydown, clearSearch,
      openActivity, openMessages, markNotification, markAllNotifications, logout,
    };
  },
  template: `
    <div class="app-shell">
      <aside class="sidebar">
        <RouterLink class="brand" to="/">
          <span class="brand-mark">🫀</span>
          <span class="brand-text">
            <strong>{{ store.brand.name }}</strong>
            <em>ECG RESEARCH DESK</em>
          </span>
        </RouterLink>
        <div class="side-caption">MAIN MENU</div>
        <nav class="nav">
          <RouterLink v-for="item in NAV_ITEMS" :key="item.key"
                      :to="item.to"
                      :class="{ on: activeNav === item.key }">
            <span class="nav-icon">{{ ({home:'⌂', analyze:'⌁', history:'▤', about:'ⓘ', research:'◫', auth:'◉'})[item.key] }}</span>
            <span>{{ item.label }}</span>
          </RouterLink>
        </nav>
        <div class="sidebar-bottom">
          <div class="side-caption">SYSTEM</div>
          <div class="system-status"><span></span>分析服务已就绪</div>
          <RouterLink class="side-support" to="/about">⚙ 系统说明</RouterLink>
        </div>
      </aside>

      <div class="app-main">
        <header class="topbar">
          <div class="topbar-inner">
            <div class="crumb"><span class="mobile-menu">☰</span><span>工作台</span><b>/</b><strong>{{ NAV_ITEMS.find(i => i.key === activeNav)?.label || '首页' }}</strong></div>
            <div class="top-actions">
              <form class="top-search" @submit.prevent="submitSearch" @focusin="activateSearch" @focusout="closeSearchSoon">
                <span class="search-icon">⌕</span><input v-model="searchText" aria-label="搜索记录或功能" placeholder="搜索历史记录或功能，如：分析" autocomplete="off" @keydown="handleSearchKeydown"><button v-if="searchText" type="button" class="search-clear" aria-label="清空搜索" @mousedown.prevent="clearSearch">×</button>
                <div class="search-panel" v-if="searchFocused">
                  <div class="search-panel-title">{{ searchQuery ? '搜索结果' : '快捷入口' }}</div>
                  <button v-for="item in searchActionResults" :key="item.key" type="button" class="search-result" @mousedown.prevent="selectSearchResult({ type: 'action', item })">
                    <span class="search-result-icon">⌁</span><span><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></span>
                  </button>
                  <div class="search-panel-title" v-if="searchHistoryResults.length">分析记录</div>
                  <button v-for="item in searchHistoryResults" :key="'history-' + item.id" type="button" class="search-result" @mousedown.prevent="selectSearchResult({ type: 'history', item })">
                    <span class="search-result-icon">▤</span><span><strong>{{ item.title || '未命名分析' }}</strong><small>{{ item.record_id || ('报告 #' + item.id) }}</small></span>
                  </button>
                  <div class="search-loading" v-if="searchLoading">正在加载分析记录…</div>
                  <div class="search-empty" v-if="!searchLoading && !searchActionResults.length && !searchHistoryResults.length">未找到匹配的功能或分析记录</div>
                </div>
              </form>
              <button type="button" class="top-icon top-action-btn" data-tooltip="科研实验：查看实验与模型可靠性指标" aria-label="科研实验：查看实验与模型可靠性指标" @click="openActivity"><span aria-hidden="true">◔</span><span class="top-action-label">科研实验</span></button>
              <div class="notification-wrap"><button type="button" class="top-icon top-action-btn" data-tooltip="系统通知：查看系统消息" aria-label="系统通知：查看系统消息" @click="openMessages">✉<b class="notification-badge" v-if="unreadNotifications">{{ unreadNotifications }}</b></button><div class="notification-panel" v-if="notificationsOpen"><div class="notification-head"><strong>系统通知</strong><button type="button" @click="markAllNotifications">全部已读</button></div><div v-if="!notifications.length" class="notification-empty">暂无通知</div><button v-for="item in notifications" :key="item.id" type="button" class="notification-item" :class="{ unread: !item.is_read }" @click="markNotification(item)"><strong>{{ item.title }}</strong><span>{{ item.body }}</span><small>{{ item.created_at }}</small></button></div></div>
              <div class="profile-wrap">
                <button type="button" class="profile" aria-label="打开账户菜单" @click="profileOpen = !profileOpen"><span class="avatar">{{ user ? (user.username || 'CL').slice(0,2).toUpperCase() : 'CL' }}</span><span>{{ user?.username || 'CardioLens' }}</span><b>⌄</b></button>
                <div class="profile-menu" v-if="profileOpen">
                  <RouterLink to="/auth" @click="profileOpen=false">{{ user ? '账户信息' : '登录 / 注册' }}</RouterLink>
                  <button v-if="user" type="button" @click="logout">退出登录</button>
                </div>
              </div>
            </div>
          </div>
        </header>

        <main class="page">
          <RouterView v-slot="{ Component }">
            <component :is="Component" />
          </RouterView>
        </main>

        <div class="toast-wrap" v-if="store.toast">
          <div class="toast" :class="store.toast.kind">{{ store.toast.message }}</div>
        </div>

        <footer class="footer">
          <div class="footer-inner">
            <div class="warn" v-if="store.disclaimer">
              <strong>⚕️ 重要声明：</strong>{{ store.disclaimer }}
            </div>
            <p class="copy">数据集来源：MIT-BIH Arrhythmia Database（PhysioNet）· 本平台用于心电智能分析科研实验与算法评估，不构成医疗诊断依据。</p>
          </div>
        </footer>
      </div>
    </div>
  `,
};
