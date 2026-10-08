import Button from "react-bootstrap/Button";
import type { Section, SectionDetails } from "./models";

type Props = {
  section: Section | SectionDetails;
};

export default function SectionJoinCallButtons({ section }: Props) {
  return (
    <>
      {section.callLink ? (
        <>
          <Button variant="success" href={section.callLink} target="_blank">
            Enter {section.name} Call
          </Button>{" "}
        </>
      ) : null}
    </>
  );
}
