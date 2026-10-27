import React from 'react';

export function RenderFailure({message}) {
  return <main className="loading" role="alert"><h2>Job Scout could not display this page</h2><p>Your saved jobs have not been deleted. Reload to return to Applications.</p><pre style={{whiteSpace:'pre-wrap',maxWidth:640}}>{message}</pre><button onClick={() => window.location.reload()}>Reload workspace</button><p>If this repeats, copy the error above when reporting it.</p></main>;
}

export class ErrorBoundary extends React.Component {
  state = {error:null};
  static getDerivedStateFromError(error) {return {error};}
  componentDidCatch(error, info) {console.error('Job Scout rendering error', error, info);}
  render() {return this.state.error ? <RenderFailure message={String(this.state.error.message || this.state.error)}/> : this.props.children;}
}
