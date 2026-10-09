import "bootstrap/dist/css/bootstrap.css";
import { useContext, useEffect, useState } from "react";
import * as React from "react";
import Col from "react-bootstrap/Col";
import Tab from "react-bootstrap/Tab";
import Tabs from "react-bootstrap/Tabs";

import Container from "react-bootstrap/Container";
import Row from "react-bootstrap/Row";
import { Navigate } from "react-router-dom";
import type { ID, SectionDetails } from "./models";
import SectionJoinCallButtons from "./SectionJoinCallButtons";
import SectionAttendance from "./SectionAttendance";
import SectionRoster from "./SectionRoster";
import SectionTabSettings from "./SectionTabSettings";
import SectionStateContext from "./SectionStateContext";
import SectionCard from "./SectionCard";
import StateContext from "./StateContext";
import Tags from "./Tags";
import useSectionAPI from "./useSectionAPI";

type Props = {
  id: ID;
};

export default function SectionPage({ id }: Props): React.ReactNode {
  const state = useContext(StateContext);

  const [section, setSection] = useState<SectionDetails | null>(null);

  const fetchSection = useSectionAPI("fetch_section", setSection);

  useEffect(() => {
    fetchSection({ section_id: id });
  }, [id, fetchSection]);

  if (!state.currentUser?.isStaff) {
    return <Navigate to="/" replace />;
  }

  if (section == null) {
    return null;
  }

  return (
    <SectionStateContext.Provider value={{ ...section, updateState: setSection }}>
      <Container>
        <br />
        <Row>
          <Col>
            <h1>
              Section #{section.id}
              <Tags tags={section.tags} />
            </h1>
            <p>
              <SectionJoinCallButtons section={section} />
            </p>
            <div className="mb-3">
              <SectionCard section={section} />
            </div>
          </Col>
        </Row>
        <Tabs transition={false}>
          <Tab eventKey={section.id} title={`${section.name} Attendance`} key={section.id}>
            <SectionAttendance section={section} />
          </Tab>
          <Tab eventKey="roster" title="Roster">
            <SectionRoster section={section} />
          </Tab>
          {state.currentUser?.isAdmin ? (
            <Tab eventKey="settings" title="Settings">
              <SectionTabSettings section={section} />
            </Tab>
          ) : null}
        </Tabs>
      </Container>
    </SectionStateContext.Provider>
  );
}
