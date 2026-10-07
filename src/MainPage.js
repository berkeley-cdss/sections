/* eslint-disable react/no-array-index-key */
// @flow strict

import * as React from "react";
import Button from "react-bootstrap/Button";

import Col from "react-bootstrap/Col";
import Container from "react-bootstrap/Container";
import Jumbotron from "react-bootstrap/Jumbotron";
import { useContext } from "react";
import Row from "react-bootstrap/Row";
import ReactMarkdown from "react-markdown";
import styled from "styled-components";

import type { Section, Time } from "./models";

import nullThrows from "./nullThrows";

import "bootstrap/dist/css/bootstrap.css";
import StateContext from "./StateContext";

const FlexLayout = styled.div`
  display: flex;
  align-items: center;
  height: 100%;
`;

export default function MainPage(): React.Node {
  const state = useContext(StateContext);

  const timeKeyLookup = new Map<string, Array<[Time, Time]>>();
  const sectionsGroupedByTime = new Map<string, Array<Section>>();

  for (const section of state.sections) {
    const interval = [[section.startTime, section.endTime]];
    const key = interval.toString();
    if (!sectionsGroupedByTime.has(key)) {
      sectionsGroupedByTime.set(key, []);
      timeKeyLookup.set(key, interval);
    }
    nullThrows(sectionsGroupedByTime.get(key)).push(section);
  }

  return (
    <>
      <Jumbotron fluid>
        <Container>
          <Row>
            <Col>
              <h1 className="display-4">{state.course} Sections</h1>
              <p className="lead">
                {/* display welcome message  */}
                <ReactMarkdown>{state.config.message}</ReactMarkdown>
              </p>
            </Col>
            {/* prompt user to login if they haven't  */}
            {state.currentUser == null ? (
              <Col>
                <FlexLayout>
                  <Button
                    block
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
      </Jumbotron>
    </>
  );
}
