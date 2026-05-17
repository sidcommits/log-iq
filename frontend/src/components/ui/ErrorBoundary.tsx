import { Component, type ReactNode } from 'react'
import { ErrorState } from './ErrorState'

interface Props { children: ReactNode }
interface State { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <ErrorState
          message={this.state.error.message || 'Something went wrong'}
          onRetry={() => this.setState({ error: null })}
        />
      )
    }
    return this.props.children
  }
}
