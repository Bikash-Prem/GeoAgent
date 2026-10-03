import React, { useEffect, useState } from 'react';
import { Nav, Footer, Toast, Page, PAGES } from './components/Shell';
import { useOps } from './lib/ops';
import Home from './pages/Home';
import Command from './pages/Command';
import Response from './pages/Response';
import Air from './pages/Air';
import WhatIf from './pages/WhatIf';
import Fleet from './pages/Fleet';
import Evidence from './pages/Evidence';

const readPage = (): Page => {
  const id = window.location.hash.replace(/^#\/?/, '').split('?')[0] as Page;
  return PAGES.some((p) => p.id === id) ? id : 'home';
};

export default function App() {
  const ops = useOps();
  const [page, setPage] = useState<Page>(readPage);
  useEffect(() => {
    const on = () => { setPage(readPage()); window.scrollTo({ top: 0 }); };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  useEffect(() => {
    const label = PAGES.find((p) => p.id === page)?.label;
    document.title = page === 'home' ? 'GeoAgentic · Emergency Decision Intelligence' : `${label} · GeoAgentic`;
  }, [page]);

  return (
    <div className="page">
      <a className="skip" href="#main">Skip to content</a>
      <Nav page={page} ops={ops} />
      <Toast ops={ops} />
      <main id="main" key={page} className="main-view">
        {page === 'home' && <Home ops={ops} />}
        {page === 'command' && <Command ops={ops} />}
        {page === 'response' && <Response ops={ops} />}
        {page === 'air' && <Air ops={ops} />}
        {page === 'whatif' && <WhatIf ops={ops} />}
        {page === 'fleet' && <Fleet ops={ops} />}
        {page === 'evidence' && <Evidence ops={ops} />}
      </main>
      <Footer ops={ops} />
    </div>
  );
}
