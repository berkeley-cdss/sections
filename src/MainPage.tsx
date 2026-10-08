import * as React from "react";
import Button from "react-bootstrap/Button";

import Col from "react-bootstrap/Col";
import Container from "react-bootstrap/Container";
import { useContext } from "react";
import Row from "react-bootstrap/Row";
import ReactMarkdown from "react-markdown";
import styled from "styled-components";

import "bootstrap/dist/css/bootstrap.css";
import Hero from "./Hero";
import StateContext from "./StateContext";

const FlexLayout = styled.div`
  display: flex;
  align-items: center;
  height: 100%;
`;

export default function MainPage(): React.ReactNode {
  const state = useContext(StateContext);

  return (
    <>
      <Hero>
        <Container>
          <Row>
            <Col>
              <h1 className="display-4">{state.course} Sections</h1>
              <div className="lead">
                {/* display welcome message  */}
                <ReactMarkdown>{state.config.message}</ReactMarkdown>
              </div>
            </Col>
            {/* prompt user to login if they haven't  */}
            {state.currentUser == null ? (
              <Col>
                <FlexLayout>
                  <Button
                    className="w-100"
                    variant="warning"
                    size="lg"
                    href={`/login/?next=${encodeURIComponent(window.location.pathname)}`}
                  >
                    Sign in
                  </Button>
                </FlexLayout>
              </Col>
            ) : null}
          </Row>
        </Container>
      </Hero>
    </>
  );
}
