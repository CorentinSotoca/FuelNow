import { Component, type ReactNode } from "react";

interface Props { children: ReactNode; }
interface State { hasError: boolean; }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "2rem", textAlign: "center", fontFamily: "system-ui, sans-serif" }}>
          <h2>Une erreur est survenue</h2>
          <p>Le chargement de la carte a échoué.</p>
          <button
            onClick={() => window.location.reload()}
            style={{ padding: "0.5rem 1rem", cursor: "pointer", marginTop: "1rem" }}
          >
            Recharger la page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
