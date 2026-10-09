import { useContext, useState } from "react";
import * as React from "react";
import Button from "react-bootstrap/Button";
import Col from "react-bootstrap/Col";
import Container from "react-bootstrap/Container";
import Row from "react-bootstrap/Row";
import ReactMarkdown from "react-markdown";
import styled from "styled-components";
import EnrolledSectionCard from "./EnrolledSectionCard";
import Hero from "./Hero";
import ToggleSwitch from "./ToggleSwitch";

import type { Section, Time } from "./models";

import nullThrows from "./nullThrows";

import "bootstrap/dist/css/bootstrap.css";
import SectionCardGroup from "./SectionCardGroup";
import StateContext from "./StateContext";

const FlexLayout = styled.div`
  display: flex;
  align-items: center;
  height: 100%;
`;

// useLocal cookie helpers
function getUseLocalCookieValue(): boolean {
  // check existence of the cookie
  if (document.cookie.split(";").some((item) => item.trim().startsWith("useLocal="))) {
    const cookieVal = document.cookie.split("; ").find((row) => row.startsWith("useLocal="));
    return cookieVal != undefined && cookieVal.split("=")[1] === "true";
  } else {
    // create the cookie and set it to true
    document.cookie = "useLocal=true; SameSite=lax; Secure";
    return false;
  }
}

function setUseLocalCookieValue(toSet: boolean) {
  document.cookie = `useLocal=${toSet ? "true" : "false"}; SameSite=lax; Secure`;
}

type Props = {
  // The section's `name` on the server, e.g. "Discussion".
  sectionName: string;
  // How the page refers to these sections, e.g. "discussion".
  noun: string;
};

// The Lab, Discussion and Tutoring pages: the user's own sections, then every
// section of that type grouped by time.
export default function SectionTypePage({ sectionName, noun }: Props): React.ReactNode {
  const state = useContext(StateContext);
  // Re-render after the time zone preference (a cookie) changes.
  const [, setTimePreferenceVersion] = useState(0);

  const timeKeyLookup = new Map<string, Array<[Time, Time]>>();
  const sectionsGroupedByTime = new Map<string, Array<Section>>();

  const typeSections = state.sections.filter((section) => section.name === sectionName);
  for (const section of typeSections) {
    const interval: Array<[Time, Time]> = [[section.startTime, section.endTime]];
    const key = interval.toString();
    if (!sectionsGroupedByTime.has(key)) {
      sectionsGroupedByTime.set(key, []);
      timeKeyLookup.set(key, interval);
    }
    nullThrows(sectionsGroupedByTime.get(key)).push(section);
  }

  const sortedIntervals: Array<Array<[Time, Time]>> = Array.from(timeKeyLookup.values()).sort(
    (t1, t2) => {
      for (let i = 0; i !== Math.max(t1.length, t2.length); ++i) {
        const [s1, e1] = t1[i] ?? [0, 0];
        const [s2, e2] = t2[i] ?? [0, 0];
        if (s1 === s2 && e1 === e2) {
          // pass
        } else if (s1 < s2 || (s1 === s2 && e1 < e2)) {
          return -1;
        } else {
          return 1;
        }
      }
      return 0;
    }
  );

  const toggleUseLocalDefault = getUseLocalCookieValue();

  function updateTimePreferences(useLocalTime: boolean) {
    setUseLocalCookieValue(useLocalTime);
    setTimePreferenceVersion((v) => v + 1);
  }

  return (
    <>
      <Hero>
        <Container>
          <Row>
            <Col>
              <h1 className="display-4">
                {state.course} {sectionName} Sections
              </h1>
            </Col>
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
          {typeSections.length === 0 ? (
            <ReactMarkdown>{`Course staff has not yet set up ${noun} sections.`}</ReactMarkdown>
          ) : null}
          {state.currentUser?.isStaff
            ? state.taughtSections
                .filter((section) => section.name === sectionName)
                .map((section, i) => (
                  <div key={section.id}>
                    {i !== 0 && <br />}
                    <EnrolledSectionCard section={section} />
                  </div>
                ))
            : state.enrolledSections == null || state.enrolledSections.length === 0
              ? null
              : state.enrolledSections
                  .filter((section) => section.name === sectionName)
                  .map((section) => <EnrolledSectionCard key={section.id} section={section} />)}
        </Container>
      </Hero>
      <Container>
        {sortedIntervals.length !== 0 ? (
          <ToggleSwitch
            defaultChecked={toggleUseLocalDefault}
            offText="Pacific"
            onText="Local"
            onChange={updateTimePreferences}
          />
        ) : null}
        {sortedIntervals.map((interval) => (
          <Row key={interval.toString()}>
            <Col>
              <SectionCardGroup sections={nullThrows(sectionsGroupedByTime.get(interval.toString()))} />
              <br />
            </Col>
          </Row>
        ))}
      </Container>
    </>
  );
}
