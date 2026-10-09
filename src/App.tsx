import { useCallback, useEffect, useState } from "react";
import * as React from "react";
import Container from "react-bootstrap/Container";

import Nav from "react-bootstrap/Nav";
import Navbar from "react-bootstrap/Navbar";
import NavDropdown from "react-bootstrap/NavDropdown";
import Spinner from "react-bootstrap/Spinner";
import { BrowserRouter as Router, Link, Route, Routes, useParams } from "react-router-dom";
import LabPage from "./LabPage";
import DiscPage from "./DiscPage";
import TutoringPage from "./TutoringPage";
import AdminPage from "./AdminPage";
import COURSE_BASE from "./coursePath";
import HistoryPage from "./HistoryPage";
import MainPage from "./MainPage";

import "bootstrap/dist/css/bootstrap.css";
import MessageContext from "./MessageContext";
import Messages from "./Messages";
import type { ID, Section, State } from "./models";
import nullThrows from "./nullThrows";
import SectionPage from "./SectionPage";
import StateContext from "./StateContext";
import useAPI from "./useStateAPI";

function UserHistoryRoute() {
  const { id } = useParams();
  return <HistoryPage userID={nullThrows(id)} />;
}

function SectionRoute() {
  const { id } = useParams();
  return <SectionPage id={nullThrows(id)} />;
}

export default function App(): React.ReactNode {
  const [state, setState] = useState<State | null>(null);
  const [messages, setMessages] = useState<Array<string>>([]);

  const pushMessage = useCallback(
    (message: string) => setMessages((currMessages) => currMessages.concat([message])),
    []
  );

  const updateState = (newState: State) => {
    // preserve ordering of sections, if possible
    if (state == null || newState.sections.length !== state?.sections.length) {
      setState(newState);
      return;
    }
    const sections: Array<Section> = Array(newState.sections.length);
    const lookup = new Map<ID, number>();
    state.sections.forEach((section, i) => lookup.set(section.id, i));
    let ok = true;
    newState.sections.forEach((section) => {
      const i = lookup.get(section.id);
      if (i == null) {
        ok = false;
        return;
      }
      sections[i] = section;
    });
    if (ok) {
      newState.sections = sections;
    }
    setState(newState);
  };

  const refreshState = useAPI("refresh_state", updateState);

  useEffect(() => {
    if (state == null) {
      refreshState();
    }
  }, [state, refreshState]);

  if (state == null) {
    return (
      <div
        className="d-flex flex-column align-items-center justify-content-center text-info"
        style={{ minHeight: "100vh" }}
        role="status"
        aria-live="polite"
      >
        <Spinner animation="border" className="mb-3" />
        <span>Loading sections&hellip;</span>
      </div>
    );
  }

  const is61A = /\b61A\b/.test(state.course);

  return (
    <Router basename={COURSE_BASE}>
      <Navbar className="navbar-sections" variant="dark" expand="md">
        <Container fluid>
          <Navbar.Brand as={Link} to="/">
            <b>{state.course}</b> Sections
          </Navbar.Brand>
          <Navbar.Toggle aria-controls="navbar" />
          <Navbar.Collapse id="navbar">
            <Nav className="me-auto">
              <Link to="/" className="nav-link active">
                Home
              </Link>
              {state.currentUser?.isStaff === false && (
                <Link to="/history" className="nav-link active">
                  History
                </Link>
              )}
              {is61A && (
                <Nav.Link href="https://cs61a.org/staff/" target="_blank" active>
                  Staff
                </Nav.Link>
              )}
              <Link to="/lab" className="nav-link active">
                Lab
              </Link>
              <Link to="/disc" className="nav-link active">
                Discussion
              </Link>
              <Link to="/tutoring" className="nav-link active">
                Tutoring
              </Link>
              {state.currentUser?.isAdmin === true && (
                <Link to="/admin" className="nav-link active">
                  Admin
                </Link>
              )}
            </Nav>
            <Nav className="me-sm-2">
              {state.currentUser != null ? (
                <NavDropdown title={state.currentUser.name} active align="end">
                  <NavDropdown.Item href="/offerings">All courses</NavDropdown.Item>
                  <NavDropdown.Item href="/logout/">Log out</NavDropdown.Item>
                </NavDropdown>
              ) : null}
            </Nav>
          </Navbar.Collapse>
        </Container>
      </Navbar>
      <Messages messages={messages} onChange={setMessages} />
      <StateContext.Provider value={{ ...state, updateState }}>
        <MessageContext.Provider value={{ pushMessage }}>
          <Routes>
            <Route path="/" element={<MainPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/user/:id" element={<UserHistoryRoute />} />
            <Route path="/lab" element={<LabPage />} />
            <Route path="/disc" element={<DiscPage />} />
            <Route path="/tutoring" element={<TutoringPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/section/:id" element={<SectionRoute />} />
            <Route path="*" element={<Container>Error: Page not found</Container>} />
          </Routes>
        </MessageContext.Provider>
      </StateContext.Provider>
    </Router>
  );
}
