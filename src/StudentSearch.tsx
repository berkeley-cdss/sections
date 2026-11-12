import { useCallback, useContext, useRef, useState } from "react";
import * as React from "react";
import Button from "react-bootstrap/Button";
import Form from "react-bootstrap/Form";
import InputGroup from "react-bootstrap/InputGroup";
import Table from "react-bootstrap/Table";
import { Link } from "react-router-dom";
import type { Person, Section } from "./models";
import { sectionInterval } from "./models";
import Pronouns from "./Pronouns";
import StateContext from "./StateContext";
import useAPI from "./useAPI";

type FoundSection = Pick<
  Section,
  "id" | "name" | "startTime" | "endTime" | "location" | "staff"
>;
type FoundStudent = Person & { sections: Array<FoundSection> };

// Every student should be in one of each; tutoring is opt-in. Matches
// FLOATING_TYPES on the server.
const EXPECTED_TYPES = ["Lab", "Discussion"];

function SectionLink({ section }: { section: FoundSection }) {
  return (
    <Link to={`/section/${section.id}`}>
      {section.name}: {section.staff == null ? "No TA" : section.staff.name},{" "}
      {sectionInterval(section)}
      {section.location ? `, ${section.location}` : null}
    </Link>
  );
}

// Find students in this offering by name or email, and see their sections.
export default function StudentSearch(): React.ReactNode {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{
    query: string;
    students: Array<FoundStudent>;
  } | null>(null);

  const { sections } = useContext(StateContext);
  // Floating only means something for the types this course has sections of.
  const expectedTypes = EXPECTED_TYPES.filter((type) =>
    sections.some((section) => section.name === type),
  );

  const searchedFor = useRef("");
  const showResults = useCallback(
    (students: Array<FoundStudent>) =>
      setResults({ query: searchedFor.current, students }),
    [],
  );
  const searchStudents = useAPI("search_students", showResults);

  const search = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (trimmed === "") {
      setResults(null);
      return;
    }
    searchedFor.current = trimmed;
    searchStudents({ query: trimmed });
  };

  return (
    <div className="mb-3">
      <Form onSubmit={search}>
        <Form.Label htmlFor="student-search">
          Find a student by name or email:
        </Form.Label>
        <InputGroup>
          <Form.Control
            id="student-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. Oski or oski@berkeley.edu"
          />
          <Button type="submit" variant="outline-secondary">
            Search
          </Button>
        </InputGroup>
      </Form>
      {results != null &&
        (results.students.length === 0 ? (
          <p className="mt-2">
            No students match &ldquo;{results.query}&rdquo;.
          </p>
        ) : (
          <Table className="mt-2" size="sm" hover>
            <thead>
              <tr>
                <th>Student</th>
                <th>Email</th>
                <th>Sections</th>
              </tr>
            </thead>
            <tbody>
              {results.students.map((student) => {
                const floating = expectedTypes.filter(
                  (type) =>
                    !student.sections.some((section) => section.name === type),
                );
                return (
                  <tr key={student.id}>
                    <td>
                      <Link to={`/user/${student.id}`}>{student.name}</Link>
                      <Pronouns of={student} />
                    </td>
                    <td>{student.email}</td>
                    <td>
                      {student.sections.map((section) => (
                        <div key={section.id}>
                          <SectionLink section={section} />
                        </div>
                      ))}
                      {floating.map((type) => (
                        <div key={type}>{type}: Floating</div>
                      ))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        ))}
    </div>
  );
}
